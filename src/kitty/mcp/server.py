"""MCP (Model Context Protocol) server for Kitty.

Implements a lightweight JSON-RPC server over stdio transport,
exposing evaluation and red-teaming tools via the Model Context
Protocol.  No external MCP SDK is required — the protocol is
handled with basic JSON-RPC 2.0 messages.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON-RPC protocol helpers
# ---------------------------------------------------------------------------

_PROTOCOL_VERSION = "0.1.0"
_SERVER_INFO = {
    "name": "kitty-mcp",
    "version": _PROTOCOL_VERSION,
}


def _make_request(
    method: str, params: Optional[Dict[str, Any]] = None, *, _id: Any = 1
) -> Dict[str, Any]:
    """Build a JSON-RPC 2.0 request object."""
    msg: Dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
        "id": _id,
    }
    if params is not None:
        msg["params"] = params
    return msg


def _make_success_response(_id: Any, result: Any) -> Dict[str, Any]:
    """Build a JSON-RPC 2.0 success response."""
    return {
        "jsonrpc": "2.0",
        "id": _id,
        "result": result,
    }


def _make_error_response(_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    """Build a JSON-RPC 2.0 error response."""
    err: Dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if data is not None:
        err["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": _id,
        "error": err,
    }


def _read_line() -> Optional[str]:
    """Read a single line from stdin (UTF-8)."""
    try:
        line = sys.stdin.readline()
        if not line:
            return None
        return line.rstrip("\r\n")
    except (EOFError, OSError):
        return None


def _write_message(msg: Dict[str, Any]) -> None:
    """Write a JSON-RPC message as a single JSON line to stdout.

    Uses the MCP stdio transport framing: ``Content-Length: N\\r\\n``
    followed by a blank line and the JSON payload.
    """
    body = json.dumps(msg, ensure_ascii=False, default=str)
    header = f"Content-Length: {len(body)}\r\n\r\n"
    sys.stdout.write(header + body)
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def _eval_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run an evaluation using the Promptfoo evaluate API.

    Args:
        params: Must contain a ``config`` key with the evaluation
            configuration string (YAML or JSON).

    Returns:
        A dict with the evaluation results.
    """
    config: str = params.get("config", "")
    if not config:
        return {"error": "Missing required parameter: config"}

    try:
        from promptfoo import evaluate  # type: ignore[import-untyped]
    except ImportError:
        return {"error": "promptfoo is not installed; cannot run eval"}

    try:
        results = evaluate(config)
        return {"results": str(results)}
    except Exception as exc:
        logger.exception("Evaluation failed")
        return {"error": f"Evaluation failed: {exc}"}


async def _redteam_run_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run a red-teaming evaluation.

    Args:
        params: Must contain a ``config`` key.  Optionally accepts a
            ``plugins`` list to restrict the red-team strategies.

    Returns:
        A dict with the red-team results.
    """
    config: str = params.get("config", "")
    plugins: list[str] = params.get("plugins", [])

    if not config:
        return {"error": "Missing required parameter: config"}

    try:
        from promptfoo.redteam import run  # type: ignore[import-untyped]
    except ImportError:
        return {"error": "promptfoo redteam module is not available"}

    try:
        kwargs: Dict[str, Any] = {"config": config}
        if plugins:
            kwargs["plugins"] = plugins
        results = run(**kwargs)
        return {"results": str(results)}
    except Exception as exc:
        logger.exception("Red-team run failed")
        return {"error": f"Red-team run failed: {exc}"}


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

_TOOLS: Dict[str, Dict[str, Any]] = {
    "kitty_eval": {
        "description": "Run a Promptfoo evaluation and return results as JSON.",
        "input_schema": {
            "type": "object",
            "properties": {
                "config": {
                    "type": "string",
                    "description": "Evaluation configuration string (YAML or JSON)",
                },
            },
            "required": ["config"],
        },
        "handler": _eval_tool,
    },
    "kitty_redteam_run": {
        "description": "Run a red-teaming evaluation and return results as JSON.",
        "input_schema": {
            "type": "object",
            "properties": {
                "config": {
                    "type": "string",
                    "description": "Red-team configuration string (YAML or JSON)",
                },
                "plugins": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of red-team plugins to use",
                },
            },
            "required": ["config"],
        },
        "handler": _redteam_run_tool,
    },
}


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


class MCPServer:
    """Minimal MCP server that exposes Kitty tools via stdio transport.

    Reads JSON-RPC 2.0 requests from stdin and writes responses to
    stdout using the standard ``Content-Length`` framing.

    Supported methods:

    * ``initialize`` — MCP handshake
    * ``tools/list`` — list available tools
    * ``tools/call`` — invoke a tool
    """

    def __init__(self) -> None:
        self._initialized: bool = False

    async def run(self) -> None:
        """Enter the main loop, reading and dispatching requests."""
        logger.info("MCP server starting (protocol %s)", _PROTOCOL_VERSION)

        while True:
            line = _read_line()
            if line is None:
                logger.debug("stdin closed, shutting down")
                break

            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                _write_message(_make_error_response(None, -32700, "Parse error", str(exc)))
                continue

            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                _write_message(
                    _make_error_response(
                        request.get("id") if isinstance(request, dict) else None,
                        -32600,
                        "Invalid Request",
                    )
                )
                continue

            _id = request.get("id")
            method: str = request.get("method", "")
            params: Dict[str, Any] = request.get("params", {}) or {}

            response = await self._dispatch(method, params, _id)
            if response is not None:
                _write_message(response)

    async def _dispatch(
        self,
        method: str,
        params: Dict[str, Any],
        _id: Any,
    ) -> Optional[Dict[str, Any]]:
        """Route a JSON-RPC method to the appropriate handler.

        Args:
            method: The JSON-RPC method name.
            params: The parameters dict.
            _id: The request ID from the JSON-RPC message.

        Returns:
            A response dict, or ``None`` for notifications.
        """
        # Notifications have no id — no response sent.
        if _id is None:
            return None

        # --- initialize ---
        if method == "initialize":
            self._initialized = True
            return _make_success_response(
                _id,
                {
                    "protocolVersion": _PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {},
                    },
                    "serverInfo": _SERVER_INFO,
                },
            )

        # --- tools/list ---
        if method == "tools/list":
            tool_list = [
                {
                    "name": name,
                    "description": info["description"],
                    "inputSchema": info["input_schema"],
                }
                for name, info in _TOOLS.items()
            ]
            return _make_success_response(_id, {"tools": tool_list})

        # --- tools/call ---
        if method == "tools/call":
            tool_name: str = params.get("name", "")
            tool_args: Dict[str, Any] = params.get("arguments", {})

            tool = _TOOLS.get(tool_name)
            if tool is None:
                return _make_error_response(
                    _id,
                    -32601,
                    f"Tool not found: {tool_name}",
                )

            try:
                result = await tool["handler"](tool_args)
                return _make_success_response(
                    _id, {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
                )
            except Exception as exc:
                logger.exception("Tool %s failed", tool_name)
                return _make_error_response(
                    _id,
                    -32000,
                    f"Tool execution failed: {exc}",
                )

        # --- notifications (no id) handled above ---
        return _make_error_response(
            _id,
            -32601,
            f"Method not found: {method}",
        )

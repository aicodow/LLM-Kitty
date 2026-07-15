# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-15

### Added

- Initial release of Kitty LLM Red Team & Evaluation Framework
- Five-rail evaluation pipeline (Input → Retrieval → Dialog → Execution → Output)
- 50+ LLM Provider adapters (OpenAI, Anthropic, HTTP, Echo)
- 66+ assertion types (contains, regex, equals, llm-rubric, factuality, guardrails)
- 157+ red-team vulnerability plugins (Foundation, Harmful, Financial, Medical, etc.)
- 30+ attack strategies (base64, jailbreak, leetspeak, multilingual, crescendo, etc.)
- Plugin system with YAML manifest and Python class support
- Strategy pipeline for composing multiple attack transforms
- Typer CLI with eval, redteam, plugins, providers, server, cache commands
- FastAPI REST API with 22 endpoints for Web Dashboard integration
- MCP Server for Agent/IDE integration
- Async evaluation engine with asyncio concurrency control
- Token-bucket rate limiter with exponential backoff
- Two-tier cache (diskcache + Redis)
- SQLAlchemy async ORM (SQLite + MySQL)
- OpenTelemetry tracing (OTLP)
- Safe YAML configuration loading (Billion Laughs protection)
- Docker multi-stage build + docker-compose + K8s Helm chart
- CI/CD with GitHub Actions (lint, test matrix, security audit)
- Comprehensive test suite (unit, integration, e2e)

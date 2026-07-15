"""Plugin registry for discovering and loading red team plugins.

The :class:`PluginRegistry` provides a central repository of all
available plugins, their manifests, and factory classes. It supports
YAML-defined plugins and Python plugin packages.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, TypeVar

import yaml

from kitty.redteam.plugins.base import PluginContext, RedteamPluginBase, TestCase
from kitty.redteam.plugins.manifest import PluginManifest, Severity

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="RedteamPluginBase")


class _ManifestDrivenPlugin(RedteamPluginBase):
    """A plugin backed entirely by a :class:`PluginManifest`.

    This is used internally by the registry when loading YAML-defined
    plugins that do not have a custom Python class.
    """

    manifest: PluginManifest

    def __init__(self, manifest: PluginManifest) -> None:
        """Initialize with the given manifest.

        Args:
            manifest: The plugin manifest to drive this plugin.
        """
        self.manifest = manifest


class PluginRegistry:
    """Central registry for discovering, loading, and accessing plugins.

    The registry scans built-in directories, user home directories, and
    local project directories for YAML manifest files and Python plugin
    packages.

    Attributes:
        BUILTIN_DIR: Path to the built-in plugin directory.
        USER_DIRS: List of user plugin directory paths.
    """

    BUILTIN_DIR: Path = Path(__file__).resolve().parent / "builtin"
    USER_DIRS: list[Path] = [
        Path.home() / ".kitty" / "plugins",
        Path.cwd() / "plugins",
    ]

    _manifests: dict[str, PluginManifest] = {}
    _plugins: dict[str, RedteamPluginBase] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    @classmethod
    async def discover_all(cls) -> None:
        """Discover all plugins from built-in and user directories.

        This method is idempotent -- calling it multiple times will
        not reload already-discovered plugins unless a force option
        is later added.

        Scans:
        - Built-in category directories (e.g. ``foundation/``)
        - User home plugin directories
        - Local project plugin directories
        """
        if cls._manifests:
            logger.debug("Registry already populated; skipping discovery")
            return

        # Discover built-in category directories.
        builtin_dir = cls.BUILTIN_DIR
        if builtin_dir.is_dir():
            for category_dir in sorted(builtin_dir.iterdir()):
                if category_dir.is_dir() and not category_dir.name.startswith("_"):
                    cls._load_category_dir(category_dir, default_category=category_dir.name)

        # Discover user plugin directories.
        for user_dir in cls.USER_DIRS:
            if user_dir.is_dir():
                cls._load_category_dir(user_dir, default_category="user")

        discovered = len(cls._manifests)
        logger.info("Discovered %d plugin(s) across all directories", discovered)

    @classmethod
    def _load_category_dir(
        cls,
        directory: Path,
        default_category: str = "custom",
    ) -> None:
        """Load all plugin manifests from a category directory.

        The directory may contain:
        - ``_manifest.yaml``: Category-level metadata.
        - ``*.yaml`` / ``*.yml``: Individual plugin manifests.

        Args:
            directory: Path to the category directory.
            default_category: Fallback category if none is specified.
        """
        if not directory.is_dir():
            return

        # Load category metadata if present.
        category_meta: dict[str, Any] = {}
        category_manifest_path = directory / "_manifest.yaml"
        if category_manifest_path.is_file():
            try:
                with open(category_manifest_path, encoding="utf-8") as fh:
                    category_meta = yaml.safe_load(fh) or {}
            except Exception as exc:
                logger.warning(
                    "Failed to load category manifest %s: %s", category_manifest_path, exc
                )

        category_name = category_meta.get("category", default_category)
        category_severity = category_meta.get("category_severity", None)
        default_requires_purpose = category_meta.get("requires_purpose", True)

        # Load individual YAML manifests.
        for yaml_path in sorted(directory.glob("*.yaml")):
            if yaml_path.name == "_manifest.yaml":
                continue
            cls._load_yaml_manifest(
                yaml_path=yaml_path,
                default_category=category_name,
                default_severity=category_severity,
                default_requires_purpose=default_requires_purpose,
            )

        for yaml_path in sorted(directory.glob("*.yml")):
            if yaml_path.name == "_manifest.yml":
                continue
            cls._load_yaml_manifest(
                yaml_path=yaml_path,
                default_category=category_name,
                default_severity=category_severity,
                default_requires_purpose=default_requires_purpose,
            )

        # Load Python plugin packages (subdirectories with __init__.py).
        for subdir in directory.iterdir():
            if subdir.is_dir() and not subdir.name.startswith("_"):
                cls._load_python_plugin(subdir, default_category=category_name)

    @classmethod
    def _load_yaml_manifest(
        cls,
        yaml_path: Path,
        default_category: str = "custom",
        default_severity: str | None = None,
        default_requires_purpose: bool = True,
    ) -> None:
        """Parse a YAML file and register all plugins defined within.

        The YAML file can define a single plugin or a list of plugins
        under a top-level ``plugins`` key.

        Args:
            yaml_path: Path to the YAML manifest file.
            default_category: Fallback category if not specified.
            default_severity: Fallback severity from category manifest.
            default_requires_purpose: Fallback requires_purpose value.
        """
        try:
            with open(yaml_path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception as exc:
            logger.warning("Failed to parse YAML manifest %s: %s", yaml_path, exc)
            return

        if not isinstance(data, dict):
            logger.warning("YAML manifest %s is not a dictionary; skipping", yaml_path)
            return

        # Determine if this describes a single plugin or a list of plugins.
        plugin_dicts: list[dict[str, Any]] = []
        if "plugins" in data:
            plugin_dicts = data["plugins"]
            global_category = data.get("category", default_category)
            global_severity = data.get("category_severity", default_severity)
        else:
            plugin_dicts = [data]
            global_category = default_category
            global_severity = default_severity

        for item in plugin_dicts:
            if not isinstance(item, dict) or "id" not in item:
                continue

            plugin_id: str = item.get("id", "")
            # If the id is short (no colon), auto-prefix with the category.
            if ":" not in plugin_id:
                plugin_id = f"{global_category}:{plugin_id}"
                item = dict(item)
                item["id"] = plugin_id

            severity_str = item.get("severity") or global_severity or "medium"
            try:
                severity = Severity(severity_str)
            except ValueError:
                logger.warning(
                    "Unknown severity %r in %s; falling back to MEDIUM", severity_str, plugin_id
                )
                severity = Severity.MEDIUM

            manifest = PluginManifest(
                id=plugin_id,
                label=item.get("label", plugin_id),
                description=item.get("description", ""),
                category=item.get("category", global_category),
                severity=severity,
                tags=item.get("tags", []),
                templates=item.get("templates", []),
                assertions=item.get("assertions", []),
                vars=item.get("vars", {}),
                num_tests=item.get("num_tests", 5),
                requires_purpose=item.get("requires_purpose", default_requires_purpose),
                requires_entities=item.get("requires_entities", False),
                supported_providers=item.get("supported_providers", []),
                plugin_class=item.get("plugin_class", None),
            )

            cls._register_manifest(manifest)

    @classmethod
    def _load_python_plugin(
        cls,
        directory: Path,
        default_category: str = "custom",
    ) -> None:
        """Import a Python plugin package from a directory.

        This method checks for an ``__init__.py`` and attempts to
        import the package, looking for any :class:`RedteamPluginBase`
        subclasses within it.

        Args:
            directory: The plugin package directory.
            default_category: Fallback category for discovered plugins.
        """
        if not (directory / "__init__.py").is_file():
            return

        package_name = f"kitty.redteam.plugins.builtin.{directory.parent.name}.{directory.name}"
        try:
            module = importlib.import_module(package_name)
        except ImportError:
            # Try relative import as a fallback.
            try:
                module = importlib.import_module(directory.name)
            except ImportError:
                logger.debug("Could not import Python plugin from %s", directory)
                return

        # Scan for RedteamPluginBase subclasses in the module.
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, RedteamPluginBase)
                and attr is not RedteamPluginBase
                and attr is not _ManifestDrivenPlugin
            ):
                plugin_class: type[RedteamPluginBase] = attr
                manifest = plugin_class.manifest
                cls._manifests[manifest.id] = manifest
                cls._plugins[manifest.id] = plugin_class
                logger.debug("Loaded Python plugin %s from %s", manifest.id, package_name)

    @classmethod
    def _register_manifest(cls, manifest: PluginManifest) -> None:
        """Register a manifest in the internal dictionaries.

        If the manifest specifies a ``plugin_class``, the class is
        resolved and stored for later instantiation.

        Args:
            manifest: The manifest to register.
        """
        cls._manifests[manifest.id] = manifest

        if manifest.plugin_class:
            resolved = cls._resolve_class(manifest.plugin_class)
            if resolved is not None:
                cls._plugins[manifest.id] = resolved
        else:
            # No custom class; use _ManifestDrivenPlugin as the factory.
            cls._plugins[manifest.id] = _ManifestDrivenPlugin

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    @classmethod
    async def get(cls, plugin_id: str) -> RedteamPluginBase:
        """Retrieve a plugin instance by its ID.

        Args:
            plugin_id: The unique plugin identifier.

        Returns:
            An instance of the requested plugin.

        Raises:
            KeyError: If the plugin ID is not registered.
        """
        if not cls._manifests:
            await cls.discover_all()

        if plugin_id not in cls._plugins:
            raise KeyError(f"Plugin {plugin_id!r} not found in registry")

        factory = cls._plugins[plugin_id]
        manifest = cls._manifests[plugin_id]

        if isinstance(factory, type) and issubclass(factory, RedteamPluginBase):
            if factory is _ManifestDrivenPlugin:
                plugin = factory(manifest=manifest)
            else:
                plugin = factory()
                plugin.manifest = manifest  # type: ignore[assignment]
        else:
            raise TypeError(f"Invalid plugin factory for {plugin_id}: {type(factory)}")

        await plugin.on_loaded()
        return plugin

    @classmethod
    def get_manifest(cls, plugin_id: str) -> PluginManifest:
        """Return the manifest for a given plugin ID.

        Args:
            plugin_id: The unique plugin identifier.

        Returns:
            The plugin manifest.

        Raises:
            KeyError: If the plugin ID is not registered.
        """
        if plugin_id not in cls._manifests:
            raise KeyError(f"Manifest for plugin {plugin_id!r} not found")
        return cls._manifests[plugin_id]

    @classmethod
    def list_all(cls) -> dict[str, PluginManifest]:
        """Return all registered plugin manifests.

        Returns:
            A dictionary mapping plugin IDs to their manifests.
        """
        return dict(cls._manifests)

    @classmethod
    def list_by_category(cls, category: str) -> dict[str, PluginManifest]:
        """Return manifests filtered by category.

        Args:
            category: The category name to filter by.

        Returns:
            A dictionary of plugin IDs to manifests in the category.
        """
        return {pid: m for pid, m in cls._manifests.items() if m.category == category}

    @classmethod
    def list_by_tag(cls, tag: str) -> dict[str, PluginManifest]:
        """Return manifests filtered by tag.

        Args:
            tag: The tag value to filter by.

        Returns:
            A dictionary of plugin IDs to manifests containing the tag.
        """
        return {pid: m for pid, m in cls._manifests.items() if tag in m.tags}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _resolve_class(cls, class_path: str) -> type[RedteamPluginBase] | None:
        """Resolve a fully-qualified class reference.

        The ``class_path`` should be in the format
        ``"module.path:ClassName"``.

        Args:
            class_path: The fully-qualified class path.

        Returns:
            The resolved class, or ``None`` if resolution failed.
        """
        if ":" not in class_path:
            logger.warning(
                "Invalid plugin_class format %r; expected 'module:ClassName'", class_path
            )
            return None

        module_name, class_name = class_path.split(":", 1)
        try:
            module = importlib.import_module(module_name)
            cls_class = getattr(module, class_name)
            if isinstance(cls_class, type) and issubclass(cls_class, RedteamPluginBase):
                return cls_class
            logger.warning(
                "Class %s in %s is not a RedteamPluginBase subclass", class_name, module_name
            )
            return None
        except (ImportError, AttributeError) as exc:
            logger.warning("Failed to resolve plugin class %s: %s", class_path, exc)
            return None

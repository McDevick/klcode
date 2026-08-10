import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PluginLoader:
    """Load user tool plugins from Python modules that export a TOOL object."""

    def __init__(self, root: str):
        self.root = Path(root)

    def load_tools(self) -> dict[str, Any]:
        tools: dict[str, Any] = {}
        if not self.root.is_dir():
            logger.warning("Plugin root %s is not a directory; no tools loaded", self.root)
            return tools

        try:
            plugin_dirs = sorted(
                (entry for entry in self.root.iterdir() if entry.is_dir()),
                key=lambda entry: entry.name,
            )
        except OSError as exc:
            logger.warning("Failed to read plugin root %s: %s", self.root, exc)
            return tools
        for plugin_dir in plugin_dirs:
            path = plugin_dir / "tool.py"
            if not path.is_file():
                logger.warning("Plugin directory %s does not contain tool.py", plugin_dir)
                continue
            try:
                tool = self._load_plugin(path)
                if tool is None:
                    continue
                name = getattr(tool, "name", None)
                if not isinstance(name, str) or not name.strip():
                    logger.warning(
                        "Plugin tool in %s does not define a non-empty string name", path
                    )
                    continue
                if name in tools:
                    logger.warning(
                        "Duplicate plugin tool name %s from %s; skipping", name, path
                    )
                    continue
                tools[name] = tool
            except Exception as exc:
                logger.warning("Failed to load plugin %s: %s", path, exc)
        return tools

    def _load_plugin(self, path: Path) -> Any | None:
        module_name = f"kl_user_plugin_{path.parent.name}"
        modules_before = set(sys.modules)
        sys.path.insert(0, str(path.parent))
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                logger.warning("Failed to load plugin %s: no import spec", path)
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            finally:
                for name in set(sys.modules) - modules_before:
                    sys.modules.pop(name, None)
            tool = getattr(module, "TOOL", None)
            if tool is None:
                logger.warning("Plugin module %s does not export TOOL", path)
            return tool
        finally:
            plugin_dir = str(path.parent)
            if plugin_dir in sys.path:
                sys.path.remove(plugin_dir)

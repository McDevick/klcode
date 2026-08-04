import importlib.util
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PluginLoader:
    """Load user tool plugins from Python modules that export a TOOL object."""

    def __init__(self, root: str):
        self.root = Path(root)

    def load_tools(self) -> dict[str, object]:
        tools = {}
        plugin_paths = sorted(self.root.glob("*.py"), key=lambda path: path.name)

        for path in plugin_paths:
            if path.name == "__init__.py":
                continue

            try:
                spec = importlib.util.spec_from_file_location(path.stem, path)
                if spec is None or spec.loader is None:
                    logger.warning("Failed to load plugin %s: no import spec", path)
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            except Exception as exc:
                logger.warning("Failed to load plugin %s: %s", path, exc)
                continue

            tool = getattr(module, "TOOL", None)
            if tool is None:
                logger.warning("Plugin module %s does not export TOOL", path)
                continue

            name = getattr(tool, "name", None)
            if not name:
                logger.warning("Plugin tool in %s does not define a name", path)
                continue

            tools[name] = tool

        return tools

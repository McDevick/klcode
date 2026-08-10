"""Locate the kl_server package for runnable demos without hard-coding its directory."""

import importlib.util
import sys
from pathlib import Path


def ensure_kl_server_importable() -> None:
    if importlib.util.find_spec("kl_server") is not None:
        return
    examples_dir = Path(__file__).resolve().parent
    repo_root = examples_dir.parent
    candidates = [repo_root]
    candidates.extend(child for child in repo_root.iterdir() if child.is_dir())
    for candidate in candidates:
        package_dir = candidate / "kl_server"
        if package_dir.is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
            return
    raise RuntimeError(
        "kl_server package not found; install the server package or run from repository root"
    )

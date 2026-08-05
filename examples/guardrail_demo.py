"""Mock-LLM demo: classify a destructive shell command as critical."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _demo_import import ensure_kl_server_importable  # noqa: E402
ensure_kl_server_importable()

from kl_server.core.guardrail import DangerClassifier  # noqa: E402
from kl_server.models.action import Action  # noqa: E402


def classify_command(command: str) -> str:
    """Return the DangerClassifier level for a run_command action."""

    action = Action(
        tool="run_command",
        args={"command": command},
        task_id="demo",
        workspace=".",
    )
    return DangerClassifier().classify(action, "managed")


def main() -> None:
    command = "rm -rf /"
    level = classify_command(command)
    print(f"guardrail: command={command!r} -> {level}")
    assert level == "critical"


if __name__ == "__main__":
    main()

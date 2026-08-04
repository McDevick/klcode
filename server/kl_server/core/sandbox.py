import os
import re


_SHELL_METACHARS = re.compile(r"[;&|`$()<>%^]")
_WRAPPERS = {
    "sh",
    "bash",
    "zsh",
    "cmd",
    "cmd.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "env",
    "command",
    "sudo",
    "time",
    "find",
    "xargs",
    "eval",
    "start",
    "call",
    "timeout",
    "nohup",
    "busybox",
}


def _normalize_binary(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    if base.lower().endswith(".exe"):
        base = base[:-4]
    return os.path.normcase(base)


class SandboxPolicy:
    def __init__(self, allow: list[str], deny: list[str]):
        self.allow = {_normalize_binary(item) for item in allow}
        self.deny = {_normalize_binary(item) for item in deny}

    def allow_command(self, command: str) -> bool:
        if not command or not command.strip():
            return False
        if command.lstrip().startswith("@"):
            return False
        if any(ord(char) < 32 or ord(char) == 127 for char in command):
            return False
        if "'" in command or '"' in command or "\\" in command:
            return False
        if _SHELL_METACHARS.search(command):
            return False
        tokens = command.split()
        if "=" in tokens[0]:
            return False
        binary = _normalize_binary(tokens[0])
        if binary in self.deny or binary in _WRAPPERS:
            return False
        return not self.allow or binary in self.allow

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


def _contains_unquoted_shell_metachars(command: str) -> bool:
    """Return True when a shell metachar appears outside quoted regions.

    Quoted arguments (e.g. ``python -c "print(1)"``) are treated as data and
    do not trigger command separation; unquoted ``&&``, ``|``, ``>``, ``(``
    etc. still do.
    """
    quote: str | None = None
    for char in command:
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if _SHELL_METACHARS.search(char):
            return True
    return False


class SandboxPolicy:
    """Command allow/deny policy for the run_command tool.

    Semantics: an empty ``allow`` list means "everything is allowed except the
    ``deny`` list" (deny-list mode). A non-empty ``allow`` list restricts
    execution to exactly those binaries. Arguments may contain quotes and
    backslashes (e.g. ``python -c "print(1)"`` or Windows paths); only
    binary-name obfuscation (leading backslash or fully-quoted first token)
    is rejected.
    """

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
        if _contains_unquoted_shell_metachars(command):
            return False
        tokens = command.split()
        if "=" in tokens[0]:
            return False
        # 二进制名混淆防护：首 token 以反斜杠开头或整体被引号包裹时拒绝，
        # 但参数里的引号/反斜杠（如 -c "..."、Windows 路径）是允许的。
        if tokens[0].startswith("\\") or tokens[0].startswith(("'", '"')):
            return False
        binary = _normalize_binary(tokens[0])
        if binary in self.deny or binary in _WRAPPERS:
            return False
        return not self.allow or binary in self.allow

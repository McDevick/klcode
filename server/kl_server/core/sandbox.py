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
_SENSITIVE_ENV_RE = re.compile(
    r"(AWS_|OPENAI|ANTHROPIC|GEMINI|GOOGLE_API|GITHUB|GH_|AZURE|"
    r"SLACK|DISCORD|TELEGRAM|HUGGING|HF_|KEY|TOKEN|SECRET|PASSWORD|"
    r"CREDENTIAL|API_KEY)",
    re.I,
)
_BASE_ENV_KEYS = {
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "HOME",
    "USERPROFILE",
    "COMSPEC",
    "PATHEXT",
    "PYTHONUTF8",
    "PYTHONIOENCODING",
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


def _strip_env_assignments(command: str) -> str:
    match = re.match(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)+", command)
    return command[match.end():] if match else command


def sanitize_env(env: dict[str, str] | None = None) -> dict[str, str]:
    source = dict(os.environ if env is None else env)
    return {
        key: value
        for key, value in source.items()
        if key in _BASE_ENV_KEYS or not _SENSITIVE_ENV_RE.search(key)
    }


class SandboxPolicy:
    """Command allow/deny policy for the run_command tool.

    Semantics: an empty ``allow`` list means "everything is allowed except the
    ``deny`` list" (deny-list mode). A non-empty ``allow`` list restricts
    execution to exactly those binaries. Arguments may contain quotes and
    backslashes (e.g. ``python -c "print(1)"`` or Windows paths); only
    binary-name obfuscation (leading backslash or fully-quoted first token)
    is rejected.
    """

    def __init__(
        self,
        allow: list[str],
        deny: list[str],
        deny_all: bool = False,
        timeout: float | None = None,
        max_cpu_seconds: float | None = None,
        max_memory_mb: int | None = None,
    ):
        self.allow = {_normalize_binary(item) for item in allow}
        self.deny = {_normalize_binary(item) for item in deny}
        self.deny_all = deny_all
        self.timeout = timeout
        self.max_cpu_seconds = max_cpu_seconds
        self.max_memory_mb = max_memory_mb

    def allow_command(self, command: str) -> bool:
        if self.deny_all:
            return False
        if not command or not command.strip():
            return False
        command = _strip_env_assignments(command)
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

    def command_timeout(self) -> float | None:
        return self.timeout

    def resource_limits(self) -> dict:
        limits = {}
        if self.max_cpu_seconds is not None:
            limits["cpu_seconds"] = self.max_cpu_seconds
        if self.max_memory_mb is not None:
            limits["memory_mb"] = self.max_memory_mb
        return limits

    def command_env(self) -> dict[str, str]:
        return sanitize_env()

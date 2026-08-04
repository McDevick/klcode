import os
import re


class SandboxPolicy:
    def __init__(self, allow: list[str], deny: list[str]):
        self.allow = {os.path.normcase(item) for item in allow}
        self.deny = {os.path.normcase(item) for item in deny}

    def allow_command(self, command: str) -> bool:
        if not command or not command.strip():
            return False
        if re.search(r"[;&|`$()<>]", command):
            return False
        tokens = command.split()
        if "=" in tokens[0]:
            return False
        binary = os.path.normcase(os.path.basename(tokens[0]))
        if binary in self.deny:
            return False
        return not self.allow or binary in self.allow

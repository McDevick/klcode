class SandboxPolicy:
    def __init__(self, allow: list[str], deny: list[str]):
        self.allow = allow
        self.deny = deny

    def allow_command(self, command: str) -> bool:
        binary = command.split()[0]
        if binary in self.deny:
            return False
        return not self.allow or binary in self.allow

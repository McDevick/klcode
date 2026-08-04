import json
import re
from pathlib import Path

from kl_server.models.action import Action


class ScopeFence:
    def __init__(self, workspace: str):
        self.root = Path(workspace).resolve()

    def allow(self, path: Path | str) -> bool:
        try:
            raw = Path(path)
            if isinstance(path, str) and not path:
                return False
            if not str(raw) or "\x00" in str(raw):
                return False
            if raw.drive and not raw.root:
                return False
            candidate = raw.resolve() if raw.is_absolute() else (self.root / raw).resolve()
        except (OSError, ValueError, RuntimeError, TypeError):
            return False
        return candidate == self.root or self.root in candidate.parents


class DangerClassifier:
    COMMAND_TOOLS = {"run_command", "run_tests", "run_lint", "typecheck"}
    DANGEROUS_TOOLS = {"delete_file", "git_commit"}
    UNMANAGED_ESCALATION_TOOLS = {"write_file", "run_command", "apply_patch"}
    CRITICAL_PATTERNS = [
        "rm -rf /",
        "rm -fr /",
        "rm -r -f /",
        "rm -f -r /",
        "format c:",
        "drop database",
        "git push --force",
        "git push -f",
        "remove-item -recurse -force",
    ]

    @staticmethod
    def _is_root_target(token: str) -> bool:
        lowered = token.lower()
        return token in {"/", "\\"} or bool(re.match(r"^[a-z]:[\\/]*$", lowered)) or lowered == "c:\\"

    @staticmethod
    def _has_rm_force(tokens: list[str]) -> bool:
        combined = [token.lower() for token in tokens[1:]]
        if any(re.fullmatch(r"-[a-z]*r[a-z]*f[a-z]*", token) for token in combined):
            return True
        if any(re.fullmatch(r"-[a-z]*f[a-z]*r[a-z]*", token) for token in combined):
            return True
        has_recursive = any(token in {"-r", "--recursive"} for token in combined)
        has_force = any(token in {"-f", "--force"} for token in combined)
        return has_recursive and has_force

    def _is_critical_command(self, tokens: list[str], command: str) -> bool:
        lowered_tokens = [token.lower() for token in tokens]
        if lowered_tokens and lowered_tokens[0] == "rm":
            if self._has_rm_force(lowered_tokens) and any(self._is_root_target(token) for token in lowered_tokens[1:]):
                return True
        if "git" in lowered_tokens and "push" in lowered_tokens:
            if any(token in {"-f", "--force"} for token in lowered_tokens[2:]):
                return True
        if lowered_tokens and lowered_tokens[0] == "remove-item":
            has_recurse = any(token in {"-r", "-recurse"} for token in lowered_tokens[1:])
            has_force = any(token in {"-f", "-force"} for token in lowered_tokens[1:])
            if has_recurse and has_force and any(self._is_root_target(token) for token in lowered_tokens[1:]):
                return True
        return any(pattern in command for pattern in self.CRITICAL_PATTERNS)

    def classify(self, action: Action, workspace_mode: str = "managed") -> str:
        if action.tool in self.DANGEROUS_TOOLS:
            return "dangerous"
        if action.tool not in self.COMMAND_TOOLS:
            if workspace_mode == "unmanaged" and action.tool in self.UNMANAGED_ESCALATION_TOOLS:
                return "dangerous"
            return "normal"
        for source in (action.raw_command, action.args.get("command")):
            if not source:
                continue
            command = re.sub(r"\s+", " ", str(source)).strip().lower()
            tokens = command.split()
            if self._is_critical_command(tokens, command):
                return "critical"
        if workspace_mode == "unmanaged" and action.tool in self.UNMANAGED_ESCALATION_TOOLS:
            return "dangerous"
        return "normal"


from dataclasses import dataclass


@dataclass
class ApprovalRequest:
    action_id: str
    tool: str
    command: str
    state: str = "pending"


class HITLManager:
    def __init__(self):
        self.requests: dict[str, ApprovalRequest] = {}

    def request(self, action_id: str, tool: str, command: str) -> ApprovalRequest:
        if action_id in self.requests and self.requests[action_id].state == "pending":
            return self.requests[action_id]
        if action_id in self.requests and self.requests[action_id].state != "pending":
            raise ValueError(f"approval request already resolved: {action_id}")
        req = ApprovalRequest(action_id=action_id, tool=tool, command=command)
        self.requests[action_id] = req
        return req

    def approve(self, action_id: str) -> str:
        req = self.requests.get(action_id)
        if req is None:
            raise ValueError(f"unknown approval request: {action_id}")
        if req.state == "rejected":
            raise ValueError(f"cannot approve rejected request: {action_id}")
        req.state = "approved"
        return req.state

    def reject(self, action_id: str) -> str:
        if action_id not in self.requests:
            self.requests[action_id] = ApprovalRequest(action_id=action_id, tool="", command="")
        req = self.requests[action_id]
        if req.state == "approved":
            raise ValueError(f"cannot reject approved request: {action_id}")
        req.state = "rejected"
        return req.state


class Guardrail:
    def __init__(self, scope, sandbox, danger, hitl, workspace_mode: str = "managed"):
        self.scope = scope
        self.sandbox = sandbox
        self.danger = danger
        self.hitl = hitl
        self.workspace_mode = workspace_mode

    def check(self, action: Action) -> str:
        try:
            paths = [action.args.get("path")]
            if isinstance(action.args.get("paths"), list):
                paths.extend(action.args.get("paths"))
            patch_arg = action.args.get("patch", "")
            if patch_arg:
                paths.extend(re.findall(r"^--- (\S+)", patch_arg, re.M))
        except (TypeError, ValueError):
            return "rejected"
        for path in paths:
            if path and not self.scope.allow(path):
                return "rejected"
        command_sources = [action.raw_command, action.args.get("command")]
        for source in command_sources:
            if source and not self.sandbox.allow_command(source):
                return "rejected"
        level = self.danger.classify(action, self.workspace_mode)
        if level in {"critical", "dangerous"}:
            approval_command = " | ".join(str(source) for source in command_sources if source)
            args_key = json.dumps(action.args, sort_keys=True)
            approval_id = f"{action.task_id}:{action.tool}:{action.seq}:{approval_command}:{args_key}"
            try:
                self.hitl.request(approval_id, action.tool, approval_command)
                return "requires_approval"
            except ValueError:
                existing = self.hitl.requests.get(approval_id)
                if existing is not None and existing.state == "approved":
                    return "allowed"
                if existing is not None and existing.state == "rejected":
                    return "rejected"
                raise
        return "allowed"

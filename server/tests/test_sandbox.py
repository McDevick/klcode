from kl_server.core.sandbox import SandboxPolicy


def test_sandbox_denies_blacklisted_command():
    policy = SandboxPolicy(allow=["pytest"], deny=["rm"])
    assert policy.allow_command("pytest tests") is True
    assert policy.allow_command("rm -rf .") is False


def test_sandbox_empty_command_fails_closed():
    policy = SandboxPolicy(allow=[], deny=[])
    assert policy.allow_command("") is False
    assert policy.allow_command("   ") is False


def test_sandbox_deny_wins_over_allow():
    policy = SandboxPolicy(allow=["rm", "pytest"], deny=["rm"])
    assert policy.allow_command("rm -rf .") is False
    assert policy.allow_command("pytest -q") is True


def test_sandbox_empty_allow_allows_non_denied():
    policy = SandboxPolicy(allow=[], deny=["rm"])
    assert policy.allow_command("python -m pytest -q") is True


def test_sandbox_allow_restricts_binary():
    policy = SandboxPolicy(allow=["pytest"], deny=[])
    assert policy.allow_command("python -m pytest") is False


def test_sandbox_denies_absolute_path_and_env_prefix_and_shell_operators():
    policy = SandboxPolicy(allow=[], deny=["rm"])
    assert policy.allow_command("/usr/bin/rm -rf .") is False
    assert policy.allow_command("FOO=bar rm -rf .") is False
    assert policy.allow_command("echo hi && rm -rf .") is False
    assert policy.allow_command("echo hi | rm -rf .") is False

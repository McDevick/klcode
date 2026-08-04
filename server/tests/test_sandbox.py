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


def test_sandbox_rejects_control_quotes_and_wrappers():
    policy = SandboxPolicy(allow=[], deny=["rm"])
    assert policy.allow_command("echo hi\nrm -rf .") is False
    assert policy.allow_command("'rm' -rf .") is False
    assert policy.allow_command("\\rm -rf .") is False
    assert policy.allow_command("sh -c 'rm -rf .'") is False
    assert policy.allow_command("env rm -rf .") is False
    assert policy.allow_command("command rm -rf .") is False


def test_sandbox_normalizes_path_deny_and_allow():
    policy = SandboxPolicy(allow=["/usr/bin/pytest"], deny=["/usr/bin/rm"])
    assert policy.allow_command("/usr/bin/pytest -q") is True
    assert policy.allow_command("/usr/bin/rm -rf .") is False
    assert policy.allow_command("rm.exe -rf .") is False


def test_sandbox_rejects_windows_metachar_and_wrappers():
    policy = SandboxPolicy(allow=[], deny=["rm", "cmd"])
    assert policy.allow_command(r"r^m -rf .") is False
    assert policy.allow_command("%COMSPEC% /c echo hi") is False
    assert policy.allow_command("start rm -rf .") is False
    assert policy.allow_command("call rm -rf .") is False
    assert policy.allow_command("@rm -rf .") is False
    assert policy.allow_command("@cmd /c echo hi") is False
    assert policy.allow_command("@start rm -rf .") is False


def test_sandbox_rejects_all_control_chars():
    policy = SandboxPolicy(allow=[], deny=[])
    assert policy.allow_command("pytest\x1b") is False
    assert policy.allow_command("pytest\t") is False

from kl_server.core.sandbox import SandboxPolicy, sanitize_env


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


def test_sandbox_allows_quoted_arguments_and_windows_paths():
    policy = SandboxPolicy(allow=[], deny=["rm"])
    assert policy.allow_command('echo "hi"') is True
    assert policy.allow_command('python -c "print(1)"') is True
    assert policy.allow_command(r"C:\Python311\python.exe -m pytest -q") is True
    assert policy.allow_command(r"python.exe C:\path\to\script.py") is True


def test_sandbox_rejects_quoted_binary_name():
    policy = SandboxPolicy(allow=[], deny=["rm"])
    assert policy.allow_command('"rm" -rf .') is False


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


def test_sandbox_strips_env_assignments_before_check():
    policy = SandboxPolicy(allow=["pytest"], deny=["rm"])
    assert policy.allow_command("FOO=bar pytest -q") is True
    assert policy.allow_command("A=1 B=2 rm -rf .") is False
    assert policy.allow_command("FOO=bar") is False


def test_sandbox_deny_all_rejects_everything():
    policy = SandboxPolicy(allow=["pytest"], deny=[], deny_all=True)
    assert policy.allow_command("pytest -q") is False
    assert policy.allow_command("echo hi") is False


def test_sandbox_exposes_timeout_and_resource_limits():
    policy = SandboxPolicy(
        allow=[],
        deny=[],
        timeout=30.0,
        max_cpu_seconds=120.0,
        max_memory_mb=2048,
    )
    assert policy.command_timeout() == 30.0
    assert policy.resource_limits() == {
        "cpu_seconds": 120.0,
        "memory_mb": 2048,
    }


def test_sanitize_env_removes_credentials_and_keeps_base():
    clean = sanitize_env(
        {
            "AWS_ACCESS_KEY_ID": "secret-aws",
            "OPENAI_API_KEY": "secret-openai",
            "GITHUB_TOKEN": "secret-gh",
            "PATH": "/usr/bin",
            "SYSTEMROOT": "C:\\Windows",
            "LANG": "en_US.UTF-8",
            "OTHER_SETTING": "keep",
        }
    )

    assert "AWS_ACCESS_KEY_ID" not in clean
    assert "OPENAI_API_KEY" not in clean
    assert "GITHUB_TOKEN" not in clean
    assert clean["PATH"] == "/usr/bin"
    assert clean["SYSTEMROOT"] == "C:\\Windows"
    assert clean["LANG"] == "en_US.UTF-8"
    assert clean["OTHER_SETTING"] == "keep"

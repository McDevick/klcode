import secrets
from dataclasses import dataclass
from pathlib import Path

from kl_server.config.config import AppConfig, SandboxConfig
from kl_server.config.credentials import create_credential_store
from kl_server.config.loader import load_app_config
from kl_server.core.agent_loop import AgentLoop, LoopSettings
from kl_server.core.context import ContextAssembler, LLMSummarizer
from kl_server.core.event_logger import EventLogger
from kl_server.core.output_summarizer import OutputSummarizer
from kl_server.core.guardrail import DangerClassifier, Guardrail, HITLManager, ScopeFence
from kl_server.core.sandbox import SandboxPolicy
from kl_server.core.session_manager import SessionManager
from kl_server.core.task_manager import TaskManager
from kl_server.core.tool_executor import ToolExecutor
from kl_server.extensions import register_user_tools
from kl_server.hooks.manager import HookManager
from kl_server.mcp.adapter import McpAdapter
from kl_server.memory.store import MemoryStore
from kl_server.plugins.loader import PluginLoader
from kl_server.providers.factory import build_provider_registry
from kl_server.providers.registry import ProviderRegistry
from kl_server.skills.loader import SkillLoader
from kl_server.storage.database import Database
from kl_server.tools.builtin import register_builtin_tools
from kl_server.tools.registry import ToolRegistry


@dataclass
class AppDependencies:
    config: AppConfig
    db: Database
    sessions: SessionManager
    tasks: TaskManager
    credentials: object
    provider_registry: ProviderRegistry
    tool_registry: ToolRegistry
    executor: ToolExecutor
    logger: EventLogger
    memory: MemoryStore
    context: ContextAssembler
    loop: AgentLoop
    hooks: HookManager
    skills: SkillLoader
    mcp: McpAdapter
    plugins: PluginLoader
    config_error: str | None = None
    config_path: str | None = None


def build_app_dependencies(
    config_path,
    db_path,
    workspace,
    log_path,
    credential_store=None,
):
    config_load_error = None
    try:
        config = load_app_config(Path(config_path))
    except Exception as exc:
        config = AppConfig(sandbox=SandboxConfig(deny_all=True))
        config_load_error = str(exc)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)
    sessions = SessionManager(db)
    tasks = TaskManager(db)
    # 凭据存储：优先 OS keyring；不可用时回退到 AES 加密文件（.kl/ 下，
    # 主密码首次生成后持久化），而非纯内存（重启丢失）。
    if credential_store is not None:
        credentials = credential_store
    else:
        master_path = db_path.parent / "credentials.master"
        if master_path.exists():
            password = master_path.read_text(encoding="utf-8").strip()
        else:
            password = secrets.token_urlsafe(32)
            master_path.write_text(password, encoding="utf-8")
        credentials = create_credential_store(
            fallback_path=db_path.parent / "credentials.bin",
            password=password,
        )
    config_error = config_load_error
    try:
        providers = build_provider_registry(config, credentials)
    except ValueError as exc:
        providers = ProviderRegistry()
        config_error = str(exc)
    tools = ToolRegistry()
    register_builtin_tools(tools)
    sandbox_error = None
    try:
        sandbox_config = config.sandbox
        sandbox = SandboxPolicy(
            allow=sandbox_config.allow,
            deny=sandbox_config.deny,
            deny_all=sandbox_config.deny_all,
            timeout=sandbox_config.timeout,
            max_cpu_seconds=sandbox_config.max_cpu_seconds,
            max_memory_mb=sandbox_config.max_memory_mb,
        )
    except Exception as exc:
        sandbox = SandboxPolicy(allow=[], deny=[], deny_all=True)
        sandbox_error = str(exc)
    if sandbox_error:
        config_error = (
            f"{config_error}; " if config_error else ""
        ) + f"sandbox config invalid: {sandbox_error}"
    guardrail = Guardrail(
        scope=ScopeFence(workspace),
        sandbox=sandbox,
        danger=DangerClassifier(),
        hitl=HITLManager(),
    )
    executor = ToolExecutor(tools, guardrail=guardrail, sandbox_policy=sandbox)
    logger = EventLogger(Path(log_path))
    executor.logger = logger
    memory = MemoryStore(db_path.parent / "memory.db")
    default_max_context = 20000
    default_provider_config = config.providers.get(config.default_provider)
    if default_provider_config is not None:
        default_max_context = default_provider_config.max_context
    context = ContextAssembler(max_tokens=default_max_context)
    hooks = HookManager(config.hooks)
    skills_root = Path(workspace) / ".kl" / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    skills = SkillLoader(str(skills_root))
    mcp = McpAdapter(config.mcp)
    plugins_root = Path(workspace) / ".kl" / "tools"
    plugins_root.mkdir(parents=True, exist_ok=True)
    plugins = PluginLoader(str(plugins_root))
    register_user_tools(tools, plugins)
    try:
        provider = providers.get(config.default_provider)
    except KeyError:
        provider = providers.get("mock")
    if provider is not None:
        def _summarizer_provider():
            try:
                return providers.get(config.default_provider)
            except KeyError:
                return providers.get("mock")

        def _summarizer_model() -> str:
            resolved = _summarizer_provider()
            return config.default_model or (getattr(resolved, "model", "") or "")

        context.summarizer = LLMSummarizer(_summarizer_provider, _summarizer_model)
        executor.summarizer = OutputSummarizer(llm_summarizer=context.summarizer)
    else:
        executor.summarizer = OutputSummarizer()
    loop = AgentLoop(
        provider=provider,
        tools=executor,
        settings=LoopSettings(),
        logger=logger,
        context=context,
        memory=memory,
        hooks=hooks,
        skills=skills,
        provider_registry=providers,
        default_provider=lambda: config.default_provider,
        default_model=lambda: config.default_model,
    )
    return AppDependencies(
        config=config,
        db=db,
        sessions=sessions,
        tasks=tasks,
        credentials=credentials,
        provider_registry=providers,
        tool_registry=tools,
        executor=executor,
        logger=logger,
        memory=memory,
        context=context,
        loop=loop,
        hooks=hooks,
        skills=skills,
        mcp=mcp,
        plugins=plugins,
        config_error=config_error,
        config_path=str(Path(config_path)),
    )

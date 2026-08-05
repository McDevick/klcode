from dataclasses import dataclass
from pathlib import Path

from kl_server.config.config import AppConfig
from kl_server.config.credentials import create_credential_store
from kl_server.config.loader import load_app_config
from kl_server.core.agent_loop import AgentLoop, LoopSettings
from kl_server.core.context import ContextAssembler
from kl_server.core.event_logger import EventLogger
from kl_server.core.guardrail import DangerClassifier, Guardrail, HITLManager, ScopeFence
from kl_server.core.sandbox import SandboxPolicy
from kl_server.core.session_manager import SessionManager
from kl_server.core.task_manager import TaskManager
from kl_server.core.tool_executor import ToolExecutor
from kl_server.extensions import McpTool, register_user_tools
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


def build_app_dependencies(
    config_path,
    db_path,
    workspace,
    log_path,
    credential_store=None,
):
    config = load_app_config(Path(config_path))
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)
    sessions = SessionManager(db)
    tasks = TaskManager(db)
    credentials = credential_store or create_credential_store()
    providers = build_provider_registry(config, credentials)
    tools = ToolRegistry()
    register_builtin_tools(tools)
    guardrail = Guardrail(
        scope=ScopeFence(workspace),
        sandbox=SandboxPolicy(allow=[], deny=["rm", "git", "docker", "curl"]),
        danger=DangerClassifier(),
        hitl=HITLManager(),
    )
    executor = ToolExecutor(tools, guardrail=guardrail)
    logger = EventLogger(Path(log_path))
    memory = MemoryStore(db_path.parent / "memory.db")
    context = ContextAssembler(max_tokens=8000)
    hooks = HookManager({})
    skills = SkillLoader(str(Path(workspace) / ".kl" / "skills"))
    mcp = McpAdapter({})
    plugins = PluginLoader(str(Path(workspace) / ".kl" / "tools"))
    register_user_tools(tools, plugins)
    tools.register(McpTool(mcp))
    provider = providers.get(config.default_provider)
    loop = AgentLoop(
        provider=provider,
        tools=executor,
        settings=LoopSettings(),
        logger=logger,
        context=context,
        memory=memory,
        hooks=hooks,
        skills=skills,
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
    )

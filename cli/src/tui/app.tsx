import React, { useEffect, useRef, useState } from 'react';
import { Box, Text, useInput, useStdin, useStdout } from 'ink';
import { Header } from './components/header';
import { Messages } from './components/messages';
import { InputFooter } from './components/input-footer';
import { CommandMenu } from './components/command-menu';
import { DockedPanel } from './components/docked-panel';
import { SessionManager } from './components/session-manager';
import { SkillsMenu } from './components/skills-menu';
import { McpManager } from './components/mcp-manager';
import { ModelManager } from './components/model-manager';
import { ConnectManager } from './components/connect-manager';
import { CommandRegistry, type CommandArg, type CommandState } from './commands';
import { ApiClient, DEFAULT_BASE_URL, type SkillInfo } from '../api/client';
import { autoStartDaemon, isConnectionError } from '../api/daemon';
import { connectDaemonPresence, connectTaskEventsWithReconnect, type TaskEvent } from '../api/events';
import { ApprovalPanel, sendApprovalDecision, type ApprovalDecision } from './screens/approval';
import { theme } from './theme';
import type { ApprovalRequest, ChatMessage, RunningTask, SlashCommand } from './types';

const COMMAND_META: Array<{
  name: string;
  desc: string;
  usage?: string;
  args?: CommandArg[];
  aliases?: string[];
  available?: (state: CommandState) => boolean;
}> = [
  {
    name: '/session',
    desc: '打开会话管理',
    available: (state) => !state.running,
  },
  {
    name: '/skills',
    desc: '查看当前可用 skill',
  },
  {
    name: '/mcp',
    desc: '管理 MCP server',
  },
  {
    name: '/connect',
    desc: '配置 provider API 连接',
    aliases: ['/conn'],
    available: (state) => !state.running,
  },
  {
    name: '/status',
    desc: '查看当前状态',
  },
  {
    name: '/model',
    desc: '查看/切换模型',
  },
  {
    name: '/context',
    desc: '查看上下文占用',
  },
  {
    name: '/compact',
    desc: '压缩当前上下文',
    available: (state) => !state.running,
  },
  {
    name: '/help',
    desc: '显示帮助',
  },
  {
    name: '/abort',
    desc: '中止当前任务',
    available: (state) => state.taskId !== null,
  },
  {
    name: '/note',
    desc: '给当前任务追加说明',
    usage: '/note <说明>',
    args: [{ name: '说明', required: true }],
    available: (state) => state.taskId !== null,
  },
  {
    name: '/pause',
    desc: '暂停任务',
    available: (state) => state.taskId !== null,
  },
  {
    name: '/continue',
    desc: '继续任务',
    available: (state) => state.taskId !== null,
  },
  {
    name: '/debug',
    desc: '调试模式开关（显示轮次与原始回复）',
  },
  {
    name: '/mouse',
    desc: '开启滚轮滚动（默认关闭，鼠标随时可选中复制）',
  },
  {
    name: '/exit',
    desc: '退出 TUI',
  },
];

const SLASH_COMMANDS: SlashCommand[] = COMMAND_META.map((command) => ({
  name: command.name,
  desc: command.desc,
}));

function eventField(event: TaskEvent, key: string): unknown {
  const payload = (event.payload ?? {}) as Record<string, unknown>;
  return event[key] !== undefined ? event[key] : payload[key];
}

const APPROVAL_OPTIONS = [
  { key: 'approve', label: 'Approve' },
  { key: 'reject', label: 'Reject' },
  { key: 'abort', label: 'Abort' },
] as const;

function truncateToolText(text: string, maxLength = 120): string {
  const single = text.replace(/\s+/g, ' ').trim();
  return single.length > maxLength ? `${single.slice(0, maxLength)}…` : single;
}

function quoteToolValue(value: unknown): string {
  if (typeof value === 'string') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(quoteToolValue).join(', ')}]`;
  return JSON.stringify(value);
}

// 工具调用参数摘要：转成函数调用风格，例如 read_file("src/a.ts")。
function formatToolArgs(args: Record<string, unknown> | undefined): string {
  if (!args) return '';
  const parts: string[] = [];
  const primary: Array<readonly [string, string]> = [];
  if (typeof args.command === 'string' && args.command) {
    primary.push(['command', args.command]);
  }
  if (typeof args.path === 'string' && args.path) {
    primary.push(['path', args.path]);
  }
  if (typeof args.pattern === 'string' && args.pattern) {
    primary.push(['pattern', args.pattern]);
  }
  if (primary.length > 0) {
    parts.push(quoteToolValue(primary[0][1]));
    for (const [key, value] of primary.slice(1)) {
      parts.push(`${key}=${quoteToolValue(value)}`);
    }
  }
  if (Array.isArray(args.paths)) {
    const paths = args.paths.filter((path): path is string => typeof path === 'string');
    if (paths.length > 0) parts.push(`paths=${quoteToolValue(paths)}`);
  }
  if (typeof args.message === 'string' && args.message) {
    parts.push(`message=${quoteToolValue(truncateToolText(args.message, 80))}`);
  }
  if (typeof args.name === 'string' && args.name) {
    parts.push(`name=${quoteToolValue(args.name)}`);
  }
  if (typeof args.content === 'string' && args.content) {
    parts.push(`content=${quoteToolValue(truncateToolText(args.content, 80))}`);
  }
  if (typeof args.patch === 'string' && args.patch) {
    parts.push(`patch=${quoteToolValue(truncateToolText(args.patch, 80))}`);
  }
  if (typeof args.old_text === 'string' && args.old_text) {
    parts.push(`old_text=${quoteToolValue(truncateToolText(args.old_text, 80))}`);
  }
  if (typeof args.new_text === 'string' && args.new_text) {
    parts.push(`new_text=${quoteToolValue(truncateToolText(args.new_text, 80))}`);
  }
  if (typeof args.new_content === 'string' && args.new_content) {
    parts.push(`new_content=${quoteToolValue(truncateToolText(args.new_content, 80))}`);
  }
  if (typeof args.start_line === 'number') {
    parts.push(`start_line=${args.start_line}`);
  }
  if (typeof args.end_line === 'number') {
    parts.push(`end_line=${args.end_line}`);
  }
  if (parts.length > 0) return truncateToolText(parts.join(', '));
  return truncateToolText(
    Object.entries(args)
      .map(([key, value]) => `${key}=${quoteToolValue(value)}`)
      .join(' · '),
  );
}

// 工具结果成败：run_command 类按 exit code 判定（非零即失败），
// 其余工具按 ok/error 字段判定
function isToolOk(payload: {
  ok?: boolean;
  error?: string | null;
  output?: string;
}): boolean {
  if (payload.ok === false || payload.error) return false;
  try {
    const parsed = JSON.parse(String(payload.output ?? '')) as {
      exit_code?: unknown;
    } | null;
    if (parsed !== null && typeof parsed === 'object' && typeof parsed.exit_code === 'number') {
      return parsed.exit_code === 0;
    }
  } catch {
    // 非 JSON 输出，按 ok 字段判定
  }
  return true;
}

// 工具结果摘要：run_command 类（JSON 输出）显示 exit code + 首行输出；
// 其余工具显示输出开头（截断 80 字符），无输出回退为 ok
function summarizeToolResult(payload: {
  error?: string | null;
  output?: string;
}): string {
  if (payload.error === 'requires_approval') {
    return `warning: ${payload.error}`;
  }
  if (payload.error) return `error: ${payload.error}`;
  const output = String(payload.output ?? '');
  if (!output) return 'ok';
  let parsed: unknown = null;
  try {
    parsed = JSON.parse(output);
  } catch {
    parsed = null;
  }
  if (parsed !== null && typeof parsed === 'object') {
    const record = parsed as { exit_code?: unknown; stdout?: unknown; stderr?: unknown };
    if (typeof record.exit_code === 'number') {
      const stdout = String(record.stdout ?? '').trim();
      const stderr = String(record.stderr ?? '').trim();
      const body = (record.exit_code === 0 ? stdout : stderr || stdout)
        .split('\n')
        .filter(Boolean);
      const first = body[0] ?? '';
      const tail = body.length > 1 ? ` (+${body.length - 1} 行)` : '';
      return `exit ${record.exit_code} · ${first.slice(0, 50)}${tail}`;
    }
  }
  const single = output.replace(/\s+/g, ' ').trim();
  return single.length > 80 ? `${single.slice(0, 80)}…` : single;
}

function parseTaskManageItems(
  output: string | null | undefined,
): Array<{ title: string; done: boolean }> | undefined {
  if (!output) return undefined;
  let parsed: unknown;
  try {
    parsed = JSON.parse(output);
  } catch {
    return undefined;
  }
  if (!Array.isArray(parsed)) return undefined;
  const items = parsed
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const record = item as Record<string, unknown>;
      if (typeof record.title !== 'string') return null;
      return {
        title: record.title,
        done: record.status === 'done',
      };
    })
    .filter((item): item is { title: string; done: boolean } => item !== null);
  return items;
}


export interface AppProps {
  autoStart?: () => Promise<boolean>;
}

export function App({ autoStart }: AppProps = {}) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState('idle');
  const [isOnline, setIsOnline] = useState(false);
  const [modelName, setModelName] = useState('loading…');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [running, setRunning] = useState<RunningTask | null>(null);
  const [approval, setApproval] = useState<ApprovalRequest | null>(null);
  const [approvalIndex, setApprovalIndex] = useState(0);
  const [connectOpen, setConnectOpen] = useState(false);
  const [sessionManagerOpen, setSessionManagerOpen] = useState(false);
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsError, setSkillsError] = useState('');
  const [skillsIndex, setSkillsIndex] = useState(0);
  const [mcpOpen, setMcpOpen] = useState(false);
  const [modelManagerOpen, setModelManagerOpen] = useState(false);
  const [exitConfirm, setExitConfirm] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [menuIndex, setMenuIndex] = useState(0);
  const [scrollTop, setScrollTop] = useState(0);
  const inputRef = useRef('');
  const [cursorIndex, setCursorIndex] = useState(0);
  const cursorRef = useRef(0);
  const nextMessageId = useRef(1);
  const roundRef = useRef(0); // 当前模型轮次（llm_call 事件更新）

  const moveCursor = (next: number) => {
    const clamped = Math.max(0, Math.min(next, inputRef.current.length));
    cursorRef.current = clamped;
    setCursorIndex(clamped);
  };

  const clearInput = () => {
    inputRef.current = '';
    setInputValue('');
    cursorRef.current = 0;
    setCursorIndex(0);
  };

  // 调试模式：默认关闭（人话渲染）；开启后显示 [Agent 第N轮] 与原始回复。
  // debugRef 供事件回调读取（避免 useEffect 依赖导致 WebSocket 重连）。
  const [debugMode, setDebugMode] = useState(false);
  const debugRef = useRef(false);

  const toggleDebug = () => {
    const next = !debugRef.current;
    debugRef.current = next;
    setDebugMode(next);
    pushMessage('agent', `调试模式: ${next ? '开（显示轮次与原始回复）' : '关'}`, 'info');
  };

  // 鼠标追踪：默认关 = 鼠标拖动选择复制随时可用（滚动用键盘）；
  // /mouse 开 = 滚轮内部滚动可用（选择复制改用 Shift+拖动）。
  const [mouseTracking, setMouseTracking] = useState(false);
  const toggleMouseTracking = () => {
    const next = !mouseTracking;
    setMouseTracking(next);
    process.stdout.write(next ? '\x1b[?1000h\x1b[?1006h' : '\x1b[?1000l\x1b[?1006l');
    pushMessage(
      'agent',
      next
        ? '鼠标追踪: 开（滚轮滚动可用；选择复制请按住 Shift 拖动）'
        : '鼠标追踪: 关（鼠标选择复制随时可用；滚动用方向键/PageUp/PageDown）',
      'info',
    );
  };

  useEffect(() => {
    return () => {
      process.stdout.write('\x1b[?1000l\x1b[?1006l');
    };
  }, []);

  const pushMessage = (
    role: ChatMessage['role'],
    content: string,
    kind: ChatMessage['kind'] = 'text',
    tool?: ChatMessage['tool'],
  ) => {
    setMessages((current) => [
      ...current,
      { id: nextMessageId.current++, role, content, kind, tool },
    ]);
    setScrollTop((current) => (current === 0 ? 0 : current));
  };

  // 终端滚轮 → 按行连续滚动（鼠标追踪由 main.ts 启用）。滚轮上滚（SGR 按钮 64）
  // 查看历史，下滚（65）回到最新；方向键/PageUp/PageDown 同样可用。
  // 配置向导打开时不滚动对话区（避免对话被滚出视野）。
  // 滚轮固定 1 行，方向键 1 行，PageUp/PageDown 半屏，保持连续预览。
  const { stdin } = useStdin();
  useEffect(() => {
    // 鼠标追踪关闭时终端不发送滚轮事件，也不解析（避免误处理残留序列）
    if (!mouseTracking) return;
    const onData = (chunk: Buffer) => {
      const text = chunk.toString('utf8');
      const match = /^\x1b\[<(\d+);(\d+);(\d+)([Mm])$/.exec(text);
      if (match === null) return;
      if (connectOpen) return;
      if (sessionManagerOpen) return;
      const button = Number(match[1]);
      if (button === 64) {
        setScrollTop((current) => current + 1);
      } else if (button === 65) {
        setScrollTop((current) => Math.max(0, current - 1));
      }
    };
    stdin.on('data', onData);
    return () => {
      stdin.off('data', onData);
    };
  }, [connectOpen, mouseTracking, sessionManagerOpen]);

  useEffect(() => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    const workspace = process.cwd();
    const prepareSession = async () => {
      const sessions = await client.listSessions();
      const reusable = sessions.find(
        (session) =>
          session.workspace === workspace &&
          session.status === 'active' &&
          (session.task_count ?? 0) === 0,
      );
      if (reusable !== undefined) {
        setSessionId(reusable.id);
        setIsOnline(true);
        pushMessage('agent', `复用会话 ${reusable.id}`, 'done');
        return;
      }
      const session = await client.createSession({ workspace });
      setSessionId(session.id);
      setIsOnline(true);
      pushMessage('agent', `会话 ${session.id} 已就绪`, 'done');
    };

    const init = async () => {
      try {
        await prepareSession();
      } catch (error: unknown) {
        if (isConnectionError(error)) {
          const started = await (autoStart ?? autoStartDaemon)();
          if (started) {
            await prepareSession();
            return;
          }
        }
        setIsOnline(false);
        pushMessage('agent', `会话创建失败: ${String(error)}`, 'error');
      }
    };
    void init();
  }, [autoStart]);

  useEffect(() => {
    const presence = connectDaemonPresence({ baseUrl: DEFAULT_BASE_URL });
    return () => presence.close();
  }, []);

  useEffect(() => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    client
      .getModelConfig()
      .then((state) => {
        setModelName(state.model);
      })
      .catch(() => {
        setModelName('unknown');
      });
  }, []);

  useEffect(() => {
    if (taskId === null) return;
    const socket = connectTaskEventsWithReconnect(taskId, (event) => {
      setIsOnline(true);
      if (event.event === 'approval_request') {
        setConnectOpen(false);
        setSessionManagerOpen(false);
        setSkillsOpen(false);
        setMcpOpen(false);
        setModelManagerOpen(false);
        setApprovalIndex(0);
        const args = (eventField(event, 'args') ?? {}) as Record<string, unknown>;
        const timeoutSeconds = Number(
          eventField(event, 'timeout_seconds') ?? 300,
        );
        setApproval({
          actionId: String(eventField(event, 'action_id') ?? ''),
          tool: String(eventField(event, 'tool') ?? ''),
          command: JSON.stringify(args),
          level: String(eventField(event, 'level') ?? ''),
          deadline: Date.now() + timeoutSeconds * 1000,
        });
        pushMessage(
          'agent',
          `审批请求（${String(eventField(event, 'level') ?? '')}）: ${String(
            eventField(event, 'tool') ?? '',
          )} ${JSON.stringify(args)}`,
          'warning',
        );
        return;
      }
      if (event.event === 'task_end') {
        const status = String(event.status);
        setTaskStatus(status);
        setRunning(null);
        setExitConfirm(false);
        if (status === 'failed') {
          // 显示具体失败原因（provider 错误 / 超轮次 / 审批中止等）
          const detail = String(event.error ?? event.result ?? '未提供具体原因');
          pushMessage('agent', `任务失败: ${detail}`, 'error');
          return;
        }
        pushMessage(
          'agent',
          `任务完成: ${status}`,
          status === 'succeeded' ? 'done' : 'info',
        );
        // 原生 tool calling：无工具调用时的回复即最终回答（剥掉 mock 兼容的 DONE: 前缀）
        const result = String(event.result ?? '').trim();
        const answer =
          result.startsWith('DONE: ') ? result.slice('DONE: '.length)
          : result === 'DONE' ? ''
          : result;
        if (answer) {
          pushMessage('agent', answer, 'text');
        }
        return;
      }
      if (event.event === 'approval_complete') {
        const decision = String(eventField(event, 'decision') ?? '');
        if (decision === 'timeout') {
          setApproval(null);
          setApprovalIndex(0);
          pushMessage('agent', '审批超时，已自动拒绝该动作', 'warning');
        }
        return;
      }
      if (event.event === 'error') {
        setRunning(null);
        pushMessage('agent', `错误: ${String(event.error ?? 'unknown')}`, 'error');
        return;
      }
      if (event.event === 'llm_call') {
        // 每轮 LLM 调用的轮次号（iteration 从 0 开始），debug 模式显示用
        const payload = (event.payload ?? {}) as { iteration?: number };
        if (typeof payload.iteration === 'number') {
          roundRef.current = payload.iteration + 1;
        }
        return;
      }
      if (event.event === 'agent_message') {
        // 模型动作前的自然语言前缀：默认模式直接显示；
        // debug 模式由 llm_result 整体显示，避免重复。
        if (debugRef.current) return;
        const payload = (event.payload ?? {}) as { text?: string };
        if (payload.text) {
          pushMessage('agent', payload.text, 'text');
        }
        return;
      }
      if (event.event === 'llm_result') {
        // 默认模式：前缀由 agent_message 显示，最终回答由 task_end 显示；
        // debug 模式：显示轮次标签 + 模型说的话 + 原生 tool_calls 原文。
        if (!debugRef.current) return;
        const payload = (event.payload ?? {}) as {
          text?: string;
          tool_calls?: Array<{ name: string; arguments: string }>;
        };
        const text = String(payload.text ?? '');
        if (text.startsWith('DONE')) return; // 兼容 mock 的 DONE 前缀（由 task_end 显示）
        const callsText = (payload.tool_calls ?? [])
          .map((call) => `{"tool":"${call.name}","args":${call.arguments}}`)
          .join('\n');
        const full = [text, callsText].filter(Boolean).join('\n');
        if (full) {
          pushMessage('agent', `[Agent 第${roundRef.current}轮] ${full}`, 'text');
        }
        return;
      }
      if (event.event === 'tool_result') {
        // 工具调用作为常驻消息流（任务结束后仍可回顾），一行摘要：
        // [Tool]: run_command("python -m pytest") → ✓ exit 0 · ...
        const payload = (event.payload ?? {}) as {
          tool?: string;
          ok?: boolean;
          error?: string | null;
          args?: Record<string, unknown>;
          output?: string;
        };
        pushMessage('agent', '', 'tool', {
          name: payload.tool ?? 'tool',
          args: formatToolArgs(payload.args),
          summary: summarizeToolResult(payload),
          ok: isToolOk(payload),
          warning: payload.error === 'requires_approval',
          taskItems: parseTaskManageItems(payload.output),
        });
        setRunning((current) =>
          current === null ? current : { ...current, steps: current.steps + 1 },
        );
        return;
      }
      if (event.event === 'feedback_generation') {
        const payload = (event.payload ?? {}) as {
          tool?: string;
          category?: string;
          summary?: string;
        };
        const summary = String(payload.summary ?? '');
        const preview =
          summary.length > 120 ? `${summary.slice(0, 120)}...` : summary;
        pushMessage(
          'agent',
          `${String(payload.tool ?? 'tool')}: ${String(payload.category ?? 'unknown')}${
            preview ? `: ${preview}` : ''
          }`,
          'feedback',
        );
        return;
      }
    });
    return () => {
      socket.close?.();
    };
  }, [taskId]);

  const handleApproval = (decision: ApprovalDecision) => {
    if (approval !== null && taskId !== null) {
      sendApprovalDecision(decision, approval.actionId, taskId);
    }
    setApproval(null);
    setApprovalIndex(0);
  };

  const switchSession = (id: string, message?: string) => {
    if (running !== null) {
      pushMessage('agent', '当前任务仍在运行，请等待结束或使用 /abort', 'error');
      return false;
    }
    setSessionId(id);
    setTaskId(null);
    setTaskStatus('idle');
    setRunning(null);
    setApproval(null);
    setConnectOpen(false);
    setSessionManagerOpen(false);
    setSkillsOpen(false);
    setMcpOpen(false);
    setModelManagerOpen(false);
    setExitConfirm(false);
    setMessages([]);
    setScrollTop(0);
    if (message) {
      pushMessage('agent', message, 'done');
    }
    return true;
  };

  const loadSessionHistory = async (id: string) => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    try {
      const history = await client.getSessionHistory(id);
      const mapped: ChatMessage[] = history.map((item) => {
        if (item.type === 'user') {
          return {
            id: nextMessageId.current++,
            role: 'user',
            content: item.content ?? '',
            kind: 'text' as const,
          };
        }
        if (item.type === 'tool') {
          return {
            id: nextMessageId.current++,
            role: 'agent',
            content: '',
            kind: 'tool' as const,
            tool: {
              name: item.name ?? 'tool',
              args: formatToolArgs(item.args ?? undefined),
              summary: summarizeToolResult({
                error: item.error ?? null,
                output: item.output ?? '',
              }),
              ok: item.ok ?? false,
              warning: item.error === 'requires_approval',
              taskItems: parseTaskManageItems(item.output),
            },
          };
        }
        return {
          id: nextMessageId.current++,
          role: 'agent',
          content: item.content ?? '',
          kind:
            item.kind === 'error'
              ? ('error' as const)
              : item.kind === 'warning'
                ? ('warning' as const)
                : item.kind === 'feedback'
                  ? ('feedback' as const)
                  : ('text' as const),
        };
      });
      setMessages(mapped);
      setScrollTop(0);
      if (history.length === 0) {
        pushMessage('agent', '该会话暂无历史消息', 'info');
      }
    } catch (error: unknown) {
      pushMessage('agent', `历史加载失败: ${String(error)}`, 'error');
    }
  };

  const dispatchSlashCommand = (commandName: string, args: string[]) => {
    if (commandName === '/exit') {
      if (running !== null && !exitConfirm) {
        setExitConfirm(true);
        pushMessage('agent', '任务仍在运行，再次输入 /exit 确认退出', 'error');
        return;
      }
      process.exit(0);
    }
    setExitConfirm(false);
    if (commandName === '/help') {
      pushMessage('agent', SLASH_COMMANDS.map((c) => `${c.name} — ${c.desc}`).join('\n'), 'info');
      return;
    }
    if (commandName === '/status') {
      pushMessage(
        'agent',
        `session: ${sessionId ?? 'none'}\ntask: ${taskId ?? 'none'}\nstatus: ${taskStatus}\napproval: ${approval !== null ? 'pending' : 'none'}`,
        'info',
      );
      return;
    }
    if (commandName === '/session') {
      setSessionManagerOpen(true);
      return;
    }
    if (commandName === '/skills') {
      setSkillsOpen(true);
      setMcpOpen(false);
      setSkillsIndex(0);
      setSkills([]);
      setSkillsError('');
      setSkillsLoading(true);
      const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
      client
        .listSkills()
        .then((items) => {
          setSkills(items);
          setSkillsLoading(false);
        })
        .catch((error: unknown) => {
          setSkills([]);
          setSkillsError(String(error));
          setSkillsLoading(false);
        });
      return;
    }
    if (commandName === '/mcp') {
      setMcpOpen(true);
      setSkillsOpen(false);
      return;
    }
    if (commandName === '/connect') {
      setConnectOpen(true);
      return;
    }
    if (commandName === '/model') {
      if (args.length === 0) {
        setSkillsOpen(false);
        setMcpOpen(false);
        setModelManagerOpen(true);
        return;
      }
      const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
      const provider = args[0];
      const model = args[1];
      client
        .setModelConfig(model ? { provider, model } : { provider })
        .then((state) => {
          setModelName(state.model);
          pushMessage('agent', `模型已切换: ${state.provider} / ${state.model}`, 'done');
        })
        .catch((error: unknown) => {
          pushMessage('agent', `模型切换失败: ${String(error)}`, 'error');
        });
      return;
    }
    if (commandName === '/context') {
      if (sessionId === null) {
        pushMessage('agent', '/context: 当前无会话', 'error');
        return;
      }
      const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
      client
        .getContextStatus(sessionId)
        .then((status) => {
          const usedPercent = status.max_tokens
            ? ((status.used_tokens / status.max_tokens) * 100).toFixed(1)
            : '0.0';
          const remainingPercent = status.max_tokens
            ? ((status.remaining_tokens / status.max_tokens) * 100).toFixed(1)
            : '0.0';
          const lines = [
            `上下文: ${status.used_tokens}/${status.max_tokens} tokens (${usedPercent}%)`,
            `剩余: ${status.remaining_tokens}/${status.max_tokens} tokens (${remainingPercent}%)`,
            ...status.sections.map(
              (section) =>
                `${section.name}: ${section.tokens} tokens (${section.percent.toFixed(1)}%)`,
            ),
          ];
          pushMessage('agent', lines.join('\n'), 'info');
        })
        .catch((error: unknown) => {
          pushMessage('agent', `上下文状态读取失败: ${String(error)}`, 'error');
        });
      return;
    }
    if (commandName === '/compact') {
      if (sessionId === null) {
        pushMessage('agent', '/compact: 当前无会话', 'error');
        return;
      }
      const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
      pushMessage('agent', 'Compacting...', 'info');
      client
        .compactContext(sessionId)
        .then((status) => {
          pushMessage(
            'agent',
            `上下文已压缩，剩余 ${status.remaining_tokens}/${status.max_tokens} tokens`,
            'done',
          );
        })
        .catch((error: unknown) => {
          pushMessage('agent', `上下文压缩失败: ${String(error)}`, 'error');
        });
      return;
    }
    if (commandName === '/debug') {
      toggleDebug();
      return;
    }
    if (commandName === '/mouse') {
      toggleMouseTracking();
      return;
    }
    if (commandName === '/note') {
      const text = args.join(' ');
      if (!text) {
        pushMessage('agent', '/note <说明>: 请提供要追加的内容', 'error');
        return;
      }
      if (taskId === null) {
        pushMessage('agent', '/note: 当前无任务', 'error');
        return;
      }
      const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
      client
        .addTaskInstruction(taskId, text)
        .then(() => {
          pushMessage('agent', `已追加说明: ${text}`, 'done');
        })
        .catch((error: unknown) => {
          pushMessage('agent', `追加说明失败: ${String(error)}`, 'error');
        });
      return;
    }
    if (commandName === '/abort' || commandName === '/pause' || commandName === '/continue') {
      if (taskId === null) {
        pushMessage('agent', `${commandName}: 当前无任务`, 'info');
        return;
      }
      const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
      const action =
        commandName === '/abort'
          ? client.abortTask(taskId)
          : commandName === '/pause'
            ? client.pauseTask(taskId)
            : client.continueTask(taskId);
      void action
        .then((result) => {
          setTaskStatus(result.status);
          if (result.status === 'canceled') {
            setRunning(null);
          }
          pushMessage('agent', `任务状态: ${result.status}`, 'info');
        })
        .catch((error: unknown) => {
          pushMessage('agent', `操作失败: ${String(error)}`, 'error');
        });
      return;
    }
    pushMessage('agent', `未知命令: ${commandName}`, 'error');
  };

  const commandRegistry = new CommandRegistry();
  for (const meta of COMMAND_META) {
    commandRegistry.register({
      ...meta,
      handler: (_ctx, args) => dispatchSlashCommand(meta.name, args),
    });
  }

  const runSlashCommand = (commandName: string, args: string[]) => {
    const state: CommandState = {
      running: running !== null,
      taskId,
      sessionId,
    };
    const result = commandRegistry.run(commandName, args, state);
    if (!result.ok) {
      pushMessage('agent', result.error ?? '命令执行失败', 'error');
    }
  };

  const submitTask = (value: string) => {
    const trimmed = value.trim();
    if (trimmed === '') return;
    if (trimmed.startsWith('/')) {
      const [commandName, ...args] = trimmed.split(/\s+/);
      runSlashCommand(commandName, args);
      return;
    }
    pushMessage('user', trimmed);
    setExitConfirm(false);
    if (running !== null) {
      pushMessage('agent', '当前任务仍在运行，请等待结束或使用 /abort', 'info');
      return;
    }
    if (sessionId === null) {
      pushMessage('agent', '会话未就绪，无法提交任务', 'error');
      return;
    }
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    client
      .createTask(trimmed, sessionId)
      .then((task) => {
        setTaskId(task.id);
        setTaskStatus('pending');
        setRunning({
          taskId: task.id,
          startedAt: Date.now(),
          steps: 0,
        });
        return client.runTask(task.id).then(() => task.id);
      })
      .then((id) => {
        setTaskStatus('running');
      })
      .catch((error: unknown) => {
        setTaskId(null);
        setTaskStatus('idle');
        setRunning(null);
        pushMessage('agent', `任务提交失败: ${String(error)}`, 'error');
      });
  };

  const applySlashCommand = (command: SlashCommand) => {
    inputRef.current = `${command.name} `;
    setInputValue(inputRef.current);
    moveCursor(inputRef.current.length);
    setMenuIndex(0);
  };

  // 按输入前缀过滤命令；输入完整命令时高亮精确匹配项
  const filteredCommands = SLASH_COMMANDS.filter((command) =>
    command.name.startsWith(inputValue),
  );
  const menuOpen = inputValue.startsWith('/') && !inputValue.includes(' ') && filteredCommands.length > 0;
  const skillsPanelOpen = skillsOpen && !connectOpen && approval === null && !sessionManagerOpen;
  const mcpPanelOpen = mcpOpen && !connectOpen && approval === null && !sessionManagerOpen && !skillsOpen;
  const modelPanelOpen =
    modelManagerOpen &&
    !connectOpen &&
    approval === null &&
    !sessionManagerOpen &&
    !skillsOpen &&
    !mcpOpen;
  const connectPanelOpen =
    connectOpen &&
    approval === null &&
    !sessionManagerOpen &&
    !skillsOpen &&
    !mcpOpen &&
    !modelManagerOpen;
  const { stdout } = useStdout();
  const viewportRows = Math.max(
    1,
    (stdout.rows ?? 24) -
      (sessionManagerOpen ? 14 : 8) -
      (skillsPanelOpen ? 9 : 0) -
      (mcpPanelOpen ? 14 : 0) -
      (modelPanelOpen ? 12 : 0) -
      (connectPanelOpen ? 12 : 0) -
      (menuOpen && !connectOpen && approval === null && !sessionManagerOpen && !skillsPanelOpen && !mcpPanelOpen && !modelPanelOpen && !connectPanelOpen
        ? 9
        : 0),
  );

  useInput((input, key) => {
    // 鼠标追踪的点击/移动事件残留（如 [<0;37;12M）不进入输入框
    if (/^\[<\d+;\d+;\d+[Mm]$/.test(input)) {
      return;
    }
    if (sessionManagerOpen) {
      return; // 会话管理面板内部处理输入
    }
    if (connectOpen) {
      return; // API 连接面板内部处理输入
    }
    if (approval !== null) {
      if (key.upArrow) {
        setApprovalIndex((index) => Math.max(0, index - 1));
        return;
      }
      if (key.downArrow) {
        setApprovalIndex((index) => Math.min(APPROVAL_OPTIONS.length - 1, index + 1));
        return;
      }
      if (key.return) {
        handleApproval(APPROVAL_OPTIONS[approvalIndex].key);
        return;
      }
      if (input === 'a') {
        handleApproval('approve');
      } else if (input === 'r') {
        handleApproval('reject');
      } else if (input === 'x') {
        handleApproval('abort');
      }
      return;
    }
    if (skillsOpen) {
      if (key.upArrow) {
        setSkillsIndex((index) => Math.max(0, index - 1));
      } else if (key.downArrow) {
        setSkillsIndex((index) => Math.min(skills.length - 1, index + 1));
      } else if (key.return || key.escape) {
        setSkillsOpen(false);
      }
      return;
    }
    if (mcpOpen) {
      return; // MCP 管理面板内部处理输入
    }
    if (modelManagerOpen) {
      return; // 模型管理面板内部处理输入
    }
    if (menuOpen) {
      if (key.upArrow) {
        setMenuIndex((index) => Math.max(0, index - 1));
        return;
      }
      if (key.downArrow) {
        setMenuIndex((index) => Math.min(filteredCommands.length - 1, index + 1));
        return;
      }
      if (key.return) {
        // 输入完整命令时直接执行，而不是被菜单拦截填入其他项
        const exact = filteredCommands.find((command) => command.name === inputValue);
        if (exact !== undefined) {
          submitTask(inputValue);
          clearInput();
          setMenuIndex(0);
        } else {
          applySlashCommand(filteredCommands[Math.min(menuIndex, filteredCommands.length - 1)]);
        }
        return;
      }
      if (key.escape) {
        clearInput();
        return;
      }
    }
    if (key.return) {
      if (key.shift) {
        const cursor = cursorRef.current;
        inputRef.current =
          inputRef.current.slice(0, cursor) + '\n' + inputRef.current.slice(cursor);
        setInputValue(inputRef.current);
        moveCursor(cursor + 1);
        return;
      }
      submitTask(inputRef.current);
      clearInput();
      return;
    }
    if (key.upArrow || key.downArrow) {
      if (inputRef.current.includes('\n')) {
        const value = inputRef.current;
        const lines = value.split('\n');
        const beforeCursor = value.slice(0, cursorRef.current);
        const currentLine = beforeCursor.split('\n').length - 1;
        const currentColumn = beforeCursor.length - beforeCursor.lastIndexOf('\n') - 1;
        const nextLine = currentLine + (key.upArrow ? -1 : 1);
        if (nextLine >= 0 && nextLine < lines.length) {
          let offset = 0;
          for (let index = 0; index < nextLine; index += 1) {
            offset += lines[index].length + 1;
          }
          moveCursor(offset + Math.min(currentColumn, lines[nextLine].length));
        }
        return;
      }
      if (key.upArrow) {
        setScrollTop((current) => current + 1);
      } else {
        setScrollTop((current) => Math.max(0, current - 1));
      }
      return;
    }
    if (key.leftArrow) {
      moveCursor(cursorRef.current - 1);
      return;
    }
    if (key.rightArrow) {
      moveCursor(cursorRef.current + 1);
      return;
    }
    if (key.home) {
      const value = inputRef.current;
      moveCursor(value.lastIndexOf('\n', cursorRef.current - 1) + 1);
      return;
    }
    if (key.end) {
      const value = inputRef.current;
      const nextNewline = value.indexOf('\n', cursorRef.current);
      moveCursor(nextNewline === -1 ? value.length : nextNewline);
      return;
    }
    if (key.pageUp) {
      const page = Math.max(1, Math.floor(viewportRows / 2));
      setScrollTop((current) => current + page);
      return;
    }
    if (key.pageDown) {
      const page = Math.max(1, Math.floor(viewportRows / 2));
      setScrollTop((current) => Math.max(0, current - page));
      return;
    }
    if (key.backspace) {
      const cursor = cursorRef.current;
      if (cursor > 0) {
        inputRef.current =
          inputRef.current.slice(0, cursor - 1) + inputRef.current.slice(cursor);
        setInputValue(inputRef.current);
        moveCursor(cursor - 1);
      }
      return;
    }
    if (key.delete) {
      const cursor = cursorRef.current;
      if (cursor < inputRef.current.length) {
        inputRef.current =
          inputRef.current.slice(0, cursor) + inputRef.current.slice(cursor + 1);
        setInputValue(inputRef.current);
        moveCursor(cursor);
      }
      return;
    }
    const cursor = cursorRef.current;
    inputRef.current =
      inputRef.current.slice(0, cursor) + input + inputRef.current.slice(cursor);
    setInputValue(inputRef.current);
    moveCursor(cursor + input.length);
  });

  return (
    <Box flexDirection="column" height="100%" backgroundColor={theme.background}>
      <Header workspace={process.cwd()} isOnline={isOnline} />
      <Messages
        messages={messages}
        running={running}
        scrollTop={scrollTop}
        viewportRows={viewportRows}
        onScrollTopChange={setScrollTop}
      />
      {menuOpen && !connectOpen && approval === null && !sessionManagerOpen && !skillsPanelOpen && !mcpPanelOpen && !modelPanelOpen && !connectPanelOpen ? (
        <DockedPanel>
          <CommandMenu
            commands={filteredCommands}
            menuIndex={Math.min(menuIndex, filteredCommands.length - 1)}
          />
        </DockedPanel>
      ) : null}
      {skillsPanelOpen ? (
        <DockedPanel borderColor={theme.surfaceAlt}>
          <SkillsMenu
            skills={skills}
            menuIndex={skillsIndex}
            loading={skillsLoading}
            error={skillsError}
          />
        </DockedPanel>
      ) : null}
      {mcpPanelOpen ? (
        <DockedPanel borderColor={theme.surfaceAlt}>
          <McpManager onClose={() => setMcpOpen(false)} />
        </DockedPanel>
      ) : null}
      {modelPanelOpen ? (
        <DockedPanel borderColor={theme.surfaceAlt}>
          <ModelManager
            onClose={() => setModelManagerOpen(false)}
            onModelChanged={(model) => setModelName(model)}
          />
        </DockedPanel>
      ) : null}
      {connectPanelOpen ? (
        <DockedPanel borderColor={theme.surfaceAlt}>
          <ConnectManager onClose={() => setConnectOpen(false)} />
        </DockedPanel>
      ) : null}
      {approval !== null ? (
        <DockedPanel borderColor={theme.yellow} borderBottom>
          <Box backgroundColor={theme.surface} paddingX={1} flexDirection="column">
            <Text bold color={theme.yellow}>
              ⚠ 审批请求（{approval.level}）: {approval.tool} {approval.command}
            </Text>
            <ApprovalPanel
              tool={approval.tool}
              command={approval.command}
              level={approval.level}
              deadline={approval.deadline}
            />
            <Box flexDirection="column" alignItems="flex-end">
              {APPROVAL_OPTIONS.map((option, index) => (
                <Text key={option.key} bold color={index === approvalIndex ? theme.teal : theme.text}>
                  {index === approvalIndex ? '▸ ' : '  '}
                  {option.label}
                </Text>
              ))}
            </Box>
          </Box>
        </DockedPanel>
      ) : sessionManagerOpen ? (
        <DockedPanel borderColor={theme.surfaceAlt}>
          <SessionManager
            currentSessionId={sessionId}
            workspace={process.cwd()}
            mouseTracking={mouseTracking}
            onEnter={(id) => {
              if (switchSession(id)) {
                void loadSessionHistory(id);
              }
            }}
            onClose={() => setSessionManagerOpen(false)}
          />
        </DockedPanel>
      ) : connectPanelOpen || modelPanelOpen || mcpPanelOpen || skillsPanelOpen ? null : (
        <InputFooter
          value={inputValue}
          modelName={modelName}
          cursorIndex={cursorIndex}
          onPaste={(text) => {
            const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
            const cursor = cursorRef.current;
            inputRef.current =
              inputRef.current.slice(0, cursor) + normalized + inputRef.current.slice(cursor);
            setInputValue(inputRef.current);
            moveCursor(cursor + normalized.length);
            setMenuIndex(0);
          }}
        />
      )}
    </Box>
  );
}

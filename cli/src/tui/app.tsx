import React, { useEffect, useRef, useState } from 'react';
import { Box, Text, useInput, useStdin, useStdout } from 'ink';
import { Header } from './components/header';
import { Messages } from './components/messages';
import { InputFooter } from './components/input-footer';
import { CommandMenu } from './components/command-menu';
import { ConfigWizard } from './components/config-wizard';
import { DockedPanel } from './components/docked-panel';
import { SessionManager } from './components/session-manager';
import { ApiClient, DEFAULT_BASE_URL } from '../api/client';
import { connectTaskEvents } from '../api/events';
import { sendApprovalDecision, type ApprovalDecision } from './screens/approval';
import { theme } from './theme';
import type { ApprovalRequest, ChatMessage, RunningTask, SlashCommand } from './types';

const SLASH_COMMANDS: SlashCommand[] = [
  { name: '/session', desc: '打开会话管理' },
  { name: '/config', desc: '打开配置向导' },
  { name: '/status', desc: '查看当前状态' },
  { name: '/model', desc: '查看/切换模型' },
  { name: '/help', desc: '显示帮助' },
  { name: '/abort', desc: '中止当前任务' },
  { name: '/pause', desc: '暂停任务' },
  { name: '/continue', desc: '继续任务' },
  { name: '/debug', desc: '调试模式开关（显示轮次与原始回复）' },
  { name: '/mouse', desc: '开启滚轮滚动（默认关闭，鼠标随时可选中复制）' },
  { name: '/exit', desc: '退出 TUI' },
];

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
  const primary = [
    typeof args.command === 'string' && args.command
      ? (['command', args.command] as const)
      : null,
    typeof args.path === 'string' && args.path
      ? (['path', args.path] as const)
      : null,
    typeof args.pattern === 'string' && args.pattern
      ? (['pattern', args.pattern] as const)
      : null,
  ].filter((entry): entry is readonly [string, string] => entry !== null);
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


export function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState('idle');
  const [isOnline, setIsOnline] = useState(false);
  const [modelName, setModelName] = useState('loading…');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [running, setRunning] = useState<RunningTask | null>(null);
  const [approval, setApproval] = useState<ApprovalRequest | null>(null);
  const [approvalIndex, setApprovalIndex] = useState(0);
  const [configWizardOpen, setConfigWizardOpen] = useState(false);
  const [sessionManagerOpen, setSessionManagerOpen] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [menuIndex, setMenuIndex] = useState(0);
  const [scrollTop, setScrollTop] = useState(0);
  const inputRef = useRef('');
  const nextMessageId = useRef(1);
  const roundRef = useRef(0); // 当前模型轮次（llm_call 事件更新）
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
      if (configWizardOpen) return;
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
  }, [configWizardOpen, mouseTracking, sessionManagerOpen]);

  useEffect(() => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    const workspace = process.cwd();
    // 优先复用同工作区、active、无任务的空会话，避免每次启动都新建
    client
      .listSessions()
      .then((sessions) => {
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
        return client.createSession({ workspace }).then((session) => {
          setSessionId(session.id);
          setIsOnline(true);
          pushMessage('agent', `会话 ${session.id} 已就绪`, 'done');
        });
      })
      .catch((error: unknown) => {
        setIsOnline(false);
        pushMessage('agent', `会话创建失败: ${String(error)}`, 'error');
      });
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
    const socket = connectTaskEvents(taskId, (event) => {
      setIsOnline(true);
      if (event.event === 'approval_request') {
        setConfigWizardOpen(false);
        setSessionManagerOpen(false);
        setApprovalIndex(0);
        setApproval({
          actionId: String(event.action_id),
          tool: String(event.tool),
          command: JSON.stringify(event.args),
          level: String(event.level),
        });
        pushMessage(
          'agent',
          `审批请求（${String(event.level)}）: ${String(event.tool)} ${JSON.stringify(event.args)}`,
          'info',
        );
        return;
      }
      if (event.event === 'task_end') {
        const status = String(event.status);
        setTaskStatus(status);
        setRunning(null);
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
        });
        setRunning((current) =>
          current === null ? current : { ...current, steps: current.steps + 1 },
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
    setConfigWizardOpen(false);
    setSessionManagerOpen(false);
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
            },
          };
        }
        return {
          id: nextMessageId.current++,
          role: 'agent',
          content: item.content ?? '',
          kind: item.kind === 'error' ? ('error' as const) : ('text' as const),
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

  const runSlashCommand = (commandName: string, args: string[]) => {
    if (commandName === '/exit') {
      process.exit(0);
    }
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
    if (commandName === '/config') {
      setConfigWizardOpen(true);
      return;
    }
    if (commandName === '/model') {
      const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
      if (args.length === 0) {
        client
          .getModelConfig()
          .then((state) => {
            const lines = [
              `当前: ${state.provider} / ${state.model}`,
              '可用:',
              ...state.available.map((item) => `  ${item.provider}: ${item.model}`),
            ];
            pushMessage('agent', lines.join('\n'), 'info');
          })
          .catch((error: unknown) => {
            pushMessage('agent', `模型配置读取失败: ${String(error)}`, 'error');
          });
        return;
      }
      const provider = args[0];
      const model = args[1];
      client
        .setModelConfig(model ? { provider, model } : { provider })
        .then((state) => {
          pushMessage('agent', `模型已切换: ${state.provider} / ${state.model}`, 'done');
        })
        .catch((error: unknown) => {
          pushMessage('agent', `模型切换失败: ${String(error)}`, 'error');
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

  const submitTask = (value: string) => {
    const trimmed = value.trim();
    if (trimmed === '') return;
    if (trimmed.startsWith('/')) {
      const [commandName, ...args] = trimmed.split(/\s+/);
      runSlashCommand(commandName, args);
      return;
    }
    pushMessage('user', trimmed);
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
    setMenuIndex(0);
  };

  // 按输入前缀过滤命令；输入完整命令时高亮精确匹配项
  const filteredCommands = SLASH_COMMANDS.filter((command) =>
    command.name.startsWith(inputValue),
  );
  const menuOpen = inputValue.startsWith('/') && !inputValue.includes(' ') && filteredCommands.length > 0;
  const { stdout } = useStdout();
  const viewportRows = Math.max(
    1,
    (stdout.rows ?? 24) -
      (sessionManagerOpen ? 14 : 8) -
      (menuOpen && !configWizardOpen && approval === null && !sessionManagerOpen ? 9 : 0) -
      (configWizardOpen ? 12 : 0),
  );

  useInput((input, key) => {
    // 鼠标追踪的点击/移动事件残留（如 [<0;37;12M）不进入输入框
    if (/^\[<\d+;\d+;\d+[Mm]$/.test(input)) {
      return;
    }
    if (sessionManagerOpen) {
      return; // 会话管理面板内部处理输入
    }
    if (configWizardOpen) {
      return; // 配置向导组件内部处理输入
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
          inputRef.current = '';
          setInputValue('');
          setMenuIndex(0);
        } else {
          applySlashCommand(filteredCommands[Math.min(menuIndex, filteredCommands.length - 1)]);
        }
        return;
      }
      if (key.escape) {
        inputRef.current = '';
        setInputValue('');
        return;
      }
    }
    if (key.return) {
      if (key.shift) {
        inputRef.current += '\n';
        setInputValue(inputRef.current);
        return;
      }
      submitTask(inputRef.current);
      inputRef.current = '';
      setInputValue('');
      return;
    }
    if (key.upArrow) {
      setScrollTop((current) => current + 1);
      return;
    }
    if (key.downArrow) {
      setScrollTop((current) => Math.max(0, current - 1));
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
    if (key.backspace || key.delete) {
      inputRef.current = inputRef.current.slice(0, -1);
      setInputValue(inputRef.current);
      return;
    }
    inputRef.current += input;
    setInputValue(inputRef.current);
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
      {menuOpen && !configWizardOpen && approval === null && !sessionManagerOpen ? (
        <DockedPanel>
          <CommandMenu
            commands={filteredCommands}
            menuIndex={Math.min(menuIndex, filteredCommands.length - 1)}
          />
        </DockedPanel>
      ) : null}
      {configWizardOpen ? (
        <DockedPanel borderColor={theme.surfaceAlt}>
          <ConfigWizard
            onClose={() => setConfigWizardOpen(false)}
            onMessage={(content, kind) => pushMessage('agent', content, kind)}
          />
        </DockedPanel>
      ) : null}
      {approval !== null ? (
        <DockedPanel borderColor={theme.yellow} borderBottom>
          <Box backgroundColor={theme.surface} paddingX={1} flexDirection="column">
            <Text bold color={theme.yellow}>
              ⚠ 审批请求（{approval.level}）: {approval.tool} {approval.command}
            </Text>
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
      ) : (
        <InputFooter
          value={inputValue}
          modelName={modelName}
        />
      )}
    </Box>
  );
}

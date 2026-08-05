import React, { useEffect, useRef, useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { Header } from './components/header';
import { Messages } from './components/messages';
import { InputFooter } from './components/input-footer';
import { CommandRegistry } from '../commands/registry';
import { SessionCommand } from '../commands/session';
import { ApiClient, DEFAULT_BASE_URL } from '../api/client';
import { connectTaskEvents } from '../api/events';
import { sendApprovalDecision, type ApprovalDecision } from './screens/approval';
import { theme } from './theme';
import type { ApprovalRequest, ChatMessage, RunningTask, SlashCommand, ToolCall } from './types';

const commands = new CommandRegistry();
commands.register(SessionCommand);

const SLASH_COMMANDS: SlashCommand[] = [
  { name: '/sessions', desc: '列出历史会话' },
  { name: '/session', desc: '会话管理 new/open/rename/close/delete' },
  { name: '/config', desc: '打开配置向导' },
  { name: '/status', desc: '查看当前状态' },
  { name: '/model', desc: '查看/切换模型' },
  { name: '/help', desc: '显示帮助' },
  { name: '/abort', desc: '中止当前任务' },
  { name: '/pause', desc: '暂停任务' },
  { name: '/continue', desc: '继续任务' },
  { name: '/exit', desc: '退出 TUI' },
];

const MAX_TOKENS = 8000;
const TOKENS_PER_EVENT = 120;

export function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState('idle');
  const [isOnline, setIsOnline] = useState(false);
  const [conversationName, setConversationName] = useState('KL Code 会话');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [running, setRunning] = useState<RunningTask | null>(null);
  const [approval, setApproval] = useState<ApprovalRequest | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [menuIndex, setMenuIndex] = useState(0);
  const [offset, setOffset] = useState(0);
  const inputRef = useRef('');
  const nextMessageId = useRef(1);

  const pushMessage = (role: ChatMessage['role'], content: string, kind: ChatMessage['kind'] = 'text') => {
    setMessages((current) => [...current, { id: nextMessageId.current++, role, content, kind }]);
    setOffset(0);
  };

  useEffect(() => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    client
      .createSession({ workspace: process.cwd() })
      .then((session) => {
        setSessionId(session.id);
        setIsOnline(true);
        pushMessage('agent', `会话 ${session.id} 已就绪`, 'done');
      })
      .catch((error: unknown) => {
        setIsOnline(false);
        pushMessage('agent', `会话创建失败: ${String(error)}`, 'error');
      });
  }, []);

  useEffect(() => {
    if (taskId === null) return;
    const socket = connectTaskEvents(taskId, (event) => {
      setIsOnline(true);
      if (event.event === 'approval_request') {
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
        pushMessage(
          'agent',
          `任务完成: ${status}`,
          status === 'succeeded' ? 'done' : status === 'failed' ? 'error' : 'info',
        );
        return;
      }
      if (event.event === 'error') {
        setRunning(null);
        pushMessage('agent', `错误: ${String(event.error ?? 'unknown')}`, 'error');
        return;
      }
      setRunning((current) => {
        if (current === null) return current;
        let toolCalls = current.toolCalls;
        if (event.event === 'tool_result') {
          const payload = (event.payload ?? {}) as { tool?: string; ok?: boolean; error?: string | null };
          toolCalls = [
            ...current.toolCalls,
            {
              name: payload.tool ?? 'tool',
              args: JSON.stringify(event.payload),
              summary: payload.error ? `error: ${payload.error}` : 'ok',
            },
          ];
        }
        return { ...current, tokensUsed: current.tokensUsed + TOKENS_PER_EVENT, toolCalls };
      });
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
    if (commandName === '/config') {
      pushMessage('agent', '配置请使用 CLI 命令：kl config provider add / kl config key set', 'info');
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
    try {
      const command = commands.resolve(commandName);
      void Promise.resolve(command.run(args))
        .then((result: string) => {
          pushMessage('agent', result, 'info');
        })
        .catch((error: unknown) => {
          pushMessage('agent', `命令错误: ${String(error)}`, 'error');
        });
    } catch {
      pushMessage('agent', `未知命令: ${commandName}`, 'error');
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
        setConversationName(trimmed.slice(0, 20));
        return client.runTask(task.id).then(() => task.id);
      })
      .then((id) => {
        setTaskStatus('running');
        setRunning({
          taskId: id,
          startedAt: Date.now(),
          tokensUsed: 0,
          maxTokens: MAX_TOKENS,
          toolCalls: [],
        });
      })
      .catch((error: unknown) => {
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

  useInput((input, key) => {
    if (approval !== null) {
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
      setOffset((current) => current + 10);
      return;
    }
    if (key.downArrow) {
      setOffset((current) => Math.max(0, current - 10));
      return;
    }
    if (key.pageUp) {
      setOffset((current) => current + 20);
      return;
    }
    if (key.pageDown) {
      setOffset((current) => Math.max(0, current - 20));
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
      <Header conversationName={conversationName} isOnline={isOnline} />
      <Messages messages={messages} running={running} offset={offset} />
      {approval !== null ? (
        <Box paddingX={1}>
          <Box
            backgroundColor={theme.surface}
            borderStyle="round"
            borderColor={theme.yellow}
            paddingX={1}
          >
            <Text color={theme.yellow}>
              ⚠ 审批请求（{approval.level}）: {approval.tool} {approval.command}
            </Text>
            <Text dimColor> [a]pprove [r]eject [x]abort</Text>
          </Box>
        </Box>
      ) : (
        <InputFooter
          value={inputValue}
          menuOpen={menuOpen}
          menuIndex={Math.min(menuIndex, filteredCommands.length - 1)}
          commands={filteredCommands}
        />
      )}
    </Box>
  );
}

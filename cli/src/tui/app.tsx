import React, { useEffect, useRef, useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { ApprovalPanel, sendApprovalDecision, type ApprovalDecision } from './screens/approval';
import { ConfigWizard } from './screens/config';
import { TaskInput } from './screens/task';
import { CommandRegistry } from '../commands/registry';
import { SessionCommand } from '../commands/session';
import { ApiClient, DEFAULT_BASE_URL } from '../api/client';
import { connectTaskEvents } from '../api/events';

const commands = new CommandRegistry();
commands.register(SessionCommand);

interface ApprovalRequest {
  actionId: string;
  tool: string;
  command: string;
  level: string;
}

type EventKind = 'info' | 'success' | 'error' | 'warning';

interface UiEvent {
  text: string;
  kind: EventKind;
}

const EVENT_COLORS: Record<EventKind, string> = {
  info: 'white',
  success: 'green',
  error: 'red',
  warning: 'yellow',
};

export function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState('idle');
  const [events, setEvents] = useState<UiEvent[]>([]);
  const [approval, setApproval] = useState<ApprovalRequest | null>(null);
  const [showConfig, setShowConfig] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const inputRef = useRef('');

  const pushEvent = (text: string, kind: EventKind = 'info') => {
    setEvents((current) => [...current, { text, kind }]);
  };

  useEffect(() => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    client
      .createSession({ workspace: process.cwd() })
      .then((session) => {
        setSessionId(session.id);
        pushEvent(`session ${session.id} ready`, 'success');
      })
      .catch((error: unknown) => {
        pushEvent(`session error: ${String(error)}`, 'error');
      });
  }, []);

  useEffect(() => {
    if (taskId === null) return;
    const socket = connectTaskEvents(taskId, (event) => {
      if (event.event === 'approval_request') {
        setApproval({
          actionId: String(event.action_id),
          tool: String(event.tool),
          command: JSON.stringify(event.args),
          level: String(event.level),
        });
        pushEvent(
          `approval required (${String(event.level)}): ${String(event.tool)} ${JSON.stringify(event.args)}`,
          'warning',
        );
        return;
      }
      if (event.event === 'task_end') {
        const status = String(event.status);
        setTaskStatus(status);
        pushEvent(
          `task ${taskId} ended: ${status}`,
          status === 'succeeded' ? 'success' : status === 'failed' ? 'error' : 'warning',
        );
        return;
      }
      if (event.event === 'error') {
        pushEvent(String(event.error ?? 'error'), 'error');
        return;
      }
      pushEvent(String(event.event));
    });
    return () => {
      socket.close?.();
    };
  }, [taskId]);

  const submitTask = (value: string) => {
    if (value === '/config' || value === '/cfg') {
      setShowConfig(true);
      return;
    }
    setShowConfig(false);
    if (value.startsWith('/')) {
      const [commandName, ...args] = value.trim().split(/\s+/);
      if (commandName === '/exit') {
        process.exit(0);
      }
      if (commandName === '/help') {
        pushEvent(commands.help());
        pushEvent('/status /abort /pause /continue /exit');
        return;
      }
      if (commandName === '/status') {
        pushEvent(
          `session: ${sessionId ?? 'none'}  task: ${taskId ?? 'none'}  status: ${taskStatus}  approval: ${approval !== null ? 'pending' : 'none'}`,
        );
        return;
      }
      if (commandName === '/abort' || commandName === '/pause' || commandName === '/continue') {
        if (taskId === null) {
          pushEvent(`${commandName}: no task`, 'warning');
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
            pushEvent(`task ${result.status}`);
          })
          .catch((error: unknown) => {
            pushEvent(`task error: ${String(error)}`, 'error');
          });
        return;
      }
      try {
        const command = commands.resolve(commandName);
        void Promise.resolve(command.run(args))
          .then((result: string) => {
            pushEvent(result);
          })
          .catch((error: unknown) => {
            pushEvent(`command error: ${String(error)}`, 'error');
          });
      } catch {
        pushEvent(`unknown command: ${commandName}`, 'warning');
      }
      return;
    }
    if (sessionId === null) {
      pushEvent('task error: no session', 'error');
      return;
    }
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    client
      .createTask(value, sessionId)
      .then((task) => {
        setTaskId(task.id);
        setTaskStatus('pending');
        pushEvent(`task ${task.id} created`);
        return client.runTask(task.id);
      })
      .then(() => {
        setTaskStatus('running');
        pushEvent('task running');
      })
      .catch((error: unknown) => {
        pushEvent(`task error: ${String(error)}`, 'error');
      });
  };

  const handleApproval = (decision: ApprovalDecision) => {
    if (approval !== null && taskId !== null) {
      sendApprovalDecision(decision, approval.actionId, taskId);
    }
    setApproval(null);
  };

  useInput((input, key) => {
    if (approval !== null) {
      if (input === 'a') {
        handleApproval('approve');
      } else if (input === 'r') {
        handleApproval('reject');
      } else if (input === 'x') {
        handleApproval('abort');
      } else if (input === 'm') {
        setApproval(null);
      }
      return;
    }
    if (showConfig) {
      return;
    }
    if (key.return) {
      submitTask(inputRef.current);
      inputRef.current = '';
      setInputValue('');
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

  const statusColor =
    taskStatus === 'failed'
      ? 'red'
      : taskStatus === 'succeeded' || taskStatus === 'canceled'
        ? 'green'
        : taskStatus === 'running'
          ? 'cyan'
          : 'white';

  return (
    <Box flexDirection="column">
      <Box borderStyle="single" borderColor="cyan" paddingX={1}>
        <Text bold color="cyan">
          KL Code
        </Text>
        <Text> session: {sessionId ?? 'none'}</Text>
        <Text> task: {taskId ?? 'none'}</Text>
        <Text color={statusColor}> status: {taskStatus}</Text>
      </Box>
      <Box flexGrow={1} flexDirection="column" paddingX={1}>
        {events.map((event, index) => (
          <Text key={index} color={EVENT_COLORS[event.kind]}>
            {event.text}
          </Text>
        ))}
      </Box>
      {approval ? (
        <ApprovalPanel tool={approval.tool} command={approval.command} level={approval.level} />
      ) : showConfig ? (
        <ConfigWizard />
      ) : (
        <TaskInput value={inputValue} />
      )}
    </Box>
  );
}

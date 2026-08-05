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

export function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [approval, setApproval] = useState<ApprovalRequest | null>(null);
  const [showConfig, setShowConfig] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const inputRef = useRef('');

  useEffect(() => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    client
      .createSession({ workspace: process.cwd() })
      .then((session) => {
        setSessionId(session.id);
        setEvents((current) => [...current, `session ${session.id} ready`]);
      })
      .catch((error: unknown) => {
        setEvents((current) => [...current, `session error: ${String(error)}`]);
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
        return;
      }
      if (event.event === 'task_end') {
        setEvents((current) => [...current, `task ${taskId} ended: ${String(event.status)}`]);
        return;
      }
      setEvents((current) => [...current, String(event.event)]);
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
        setEvents((current) => [
          ...current,
          commands.help(),
          '/status /abort /pause /continue /exit',
        ]);
        return;
      }
      if (commandName === '/status') {
        setEvents((current) => [
          ...current,
          `session: ${sessionId ?? 'none'}`,
          `task: ${taskId ?? 'none'}`,
          `approval: ${approval !== null ? 'pending' : 'none'}`,
        ]);
        return;
      }
      if (commandName === '/abort' || commandName === '/pause' || commandName === '/continue') {
        if (taskId === null) {
          setEvents((current) => [...current, `${commandName}: no task`]);
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
            setEvents((current) => [...current, `task ${result.status}`]);
          })
          .catch((error: unknown) => {
            setEvents((current) => [...current, `task error: ${String(error)}`]);
          });
        return;
      }
      try {
        const command = commands.resolve(commandName);
        void Promise.resolve(command.run(args))
          .then((result: string) => {
            setEvents((current) => [...current, result]);
          })
          .catch((error: unknown) => {
            setEvents((current) => [...current, `command error: ${String(error)}`]);
          });
      } catch {
        setEvents((current) => [...current, `unknown command: ${commandName}`]);
      }
      return;
    }
    if (sessionId === null) {
      setEvents((current) => [...current, 'task error: no session']);
      return;
    }
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    client
      .createTask(value, sessionId)
      .then((task) => {
        setTaskId(task.id);
        setEvents((current) => [...current, `task ${task.id} created`]);
        return client.runTask(task.id);
      })
      .then(() => {
        setEvents((current) => [...current, 'task running']);
      })
      .catch((error: unknown) => {
        setEvents((current) => [...current, `task error: ${String(error)}`]);
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

  return (
    <Box flexDirection="column">
      <Text>KL Code</Text>
      <TaskInput value={inputValue} />
      <Text>{events.join('\n')}</Text>
      {showConfig ? <ConfigWizard /> : null}
      {approval ? (
        <ApprovalPanel tool={approval.tool} command={approval.command} level={approval.level} />
      ) : null}
    </Box>
  );
}

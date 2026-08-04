import React, { useState } from 'react';
import { Box, Text } from 'ink';
import { ApprovalPanel } from './screens/approval';
import { ConfigWizard } from './screens/config';
import { TaskInput } from './screens/task';
import { CommandRegistry } from '../commands/registry';
import { SessionCommand } from '../commands/session';

const commands = new CommandRegistry();
commands.register(SessionCommand);

export function App() {
  const [events, setEvents] = useState<string[]>([]);
  const [approval, setApproval] = useState<{ tool: string; command: string } | null>(null);
  const [showConfig, setShowConfig] = useState(false);

  return (
    <Box flexDirection="column">
      <Text>KL Code</Text>
      <TaskInput
        active={approval === null && !showConfig}
        onSubmit={(value) => {
          if (value === '/config' || value === '/cfg') {
            setShowConfig(true);
            return;
          }
          setShowConfig(false);
          if (value.startsWith('/')) {
            const [commandName, ...args] = value.trim().split(/\s+/);
            try {
              const command = commands.resolve(commandName);
              void Promise.resolve(command.run(args)).then((result: string) => {
                setEvents((current) => [...current, result]);
              }).catch((error: unknown) => {
                setEvents((current) => [...current, `command error: ${String(error)}`]);
              });
            } catch {
              setEvents((current) => [...current, `unknown command: ${commandName}`]);
            }
            return;
          }
          setEvents((current) => [...current, `task: ${value}`]);
          setApproval({ tool: 'run_command', command: value });
        }}
      />
      <Text>{events.join('\n')}</Text>
      {showConfig ? <ConfigWizard /> : null}
      {approval ? (
        <ApprovalPanel
          active
          tool={approval.tool}
          command={approval.command}
          onApprove={() => {
            setEvents((current) => [...current, 'approved']);
            setApproval(null);
          }}
          onReject={() => {
            setEvents((current) => [...current, 'rejected']);
            setApproval(null);
          }}
          onModify={() => {
            setEvents((current) => [...current, 'modify']);
          }}
        />
      ) : null}
    </Box>
  );
}

import React, { useState } from 'react';
import { Box, Text } from 'ink';
import { ApprovalPanel } from './screens/approval';
import { TaskInput } from './screens/task';

export function App() {
  const [events, setEvents] = useState<string[]>([]);
  const [approval, setApproval] = useState<{ tool: string; command: string } | null>(null);

  return (
    <Box flexDirection="column">
      <Text>KL Code</Text>
      <TaskInput
        active={approval === null}
        onSubmit={(value) => {
          setEvents((current) => [...current, `task: ${value}`]);
          setApproval({ tool: 'run_command', command: value });
        }}
      />
      <Text>{events.join('\n')}</Text>
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

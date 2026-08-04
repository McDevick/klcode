import React from 'react';
import { Box, Text } from 'ink';
import { ApprovalPanel } from './screens/approval';
import { TaskInput } from './screens/task';

export function App({ events = [] }: { events?: string[] }) {
  return (
    <Box flexDirection="column">
      <Text>KL Code</Text>
      <TaskInput onSubmit={() => {}} />
      <Text>{events.join('\n')}</Text>
      <ApprovalPanel tool="none" command="" />
    </Box>
  );
}

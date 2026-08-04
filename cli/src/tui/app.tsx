import React from 'react';
import { Box, Text } from 'ink';
import { ApprovalPanel } from './screens/approval';
import { TaskInput } from './screens/task';

export function App() {
  return (
    <Box flexDirection="column">
      <Text>KL Code</Text>
      <TaskInput onSubmit={() => {}} />
      <ApprovalPanel tool="none" command="" />
    </Box>
  );
}

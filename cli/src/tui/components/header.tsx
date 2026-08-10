import React from 'react';
import { Box, Text } from 'ink';
import { theme } from '../theme';

export function Header({
  workspace,
  isOnline,
}: {
  workspace: string;
  isOnline: boolean;
}) {
  return (
    <Box
      flexShrink={0}
      paddingX={1}
      borderStyle="single"
      borderColor={theme.border}
      borderTop
      borderBottom
      borderLeft={false}
      borderRight={false}
    >
      <Text bold color={theme.text}>
        KLCODE
      </Text>
      <Text color={isOnline ? theme.green : theme.red}> ●</Text>
      <Box flexGrow={1} />
      <Text dimColor>{workspace}</Text>
    </Box>
  );
}

import React from 'react';
import { Box, Text } from 'ink';
import { theme } from '../theme';

export function Header({
  conversationName,
  isOnline,
}: {
  conversationName: string;
  isOnline: boolean;
}) {
  return (
    <Box
      height={2}
      paddingX={1}
      backgroundColor={theme.surface}
      borderStyle="single"
      borderColor={theme.surfaceAlt}
      borderTop={false}
      borderLeft={false}
      borderRight={false}
    >
      <Text>📝 {conversationName}</Text>
      <Box flexGrow={1} />
      <Text dimColor>klcode</Text>
      <Text color={isOnline ? theme.green : theme.red}> ●</Text>
    </Box>
  );
}

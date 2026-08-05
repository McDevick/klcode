import React from 'react';
import { Box, Text } from 'ink';

export function Header({
  conversationName,
  isOnline,
}: {
  conversationName: string;
  isOnline: boolean;
}) {
  return (
    <Box paddingX={1}>
      <Text>📝 {conversationName}</Text>
      <Box flexGrow={1} />
      <Text dimColor>klcode</Text>
      <Text color={isOnline ? 'green' : 'red'}> ●</Text>
    </Box>
  );
}

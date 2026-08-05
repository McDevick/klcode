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
    <Box
      height={3}
      paddingX={1}
      backgroundColor="#1E1E2E"
      borderStyle="single"
      borderColor="#313244"
      borderTop={false}
      borderLeft={false}
      borderRight={false}
    >
      <Text>📝 {conversationName}</Text>
      <Box flexGrow={1} />
      <Text>📂 klcode</Text>
      <Text color={isOnline ? 'green' : 'red'}> ●</Text>
    </Box>
  );
}

import React from 'react';
import { Box, Text, usePaste } from 'ink';
import { theme } from '../theme';

export function InputFooter({
  value,
  modelName,
  onPaste,
  cursorIndex = 0,
}: {
  value: string;
  modelName: string;
  onPaste: (text: string) => void;
  cursorIndex?: number;
}) {
  usePaste(onPaste);

  const cursor = Math.min(cursorIndex, value.length);
  const content = `${value.slice(0, cursor)}▍${value.slice(cursor)}`;

  return (
    <Box flexDirection="column" flexShrink={0}>
      <Box
        paddingX={1}
        borderStyle="single"
        borderColor={theme.border}
        borderTop
        borderBottom
        borderLeft={false}
        borderRight={false}
      >
        <Text color={theme.teal}>&gt; {content}</Text>
      </Box>
      <Box paddingX={1}>
        <Text color={theme.blue}>model: {modelName}</Text>
      </Box>
    </Box>
  );
}

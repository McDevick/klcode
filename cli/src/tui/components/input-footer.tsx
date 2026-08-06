import React, { useEffect, useState } from 'react';
import { Box, Text } from 'ink';
import { theme } from '../theme';

export function InputFooter({
  value,
  modelName,
}: {
  value: string;
  modelName: string;
}) {
  const [cursorVisible, setCursorVisible] = useState(true);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = setInterval(() => setCursorVisible((current) => !current), 500);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const lines = value.split('\n');
  const timeStr = now.toLocaleTimeString('en-GB', { hour12: false });

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
        <Text color={theme.teal}>&gt; </Text>
        {lines.map((line, index) => (
          <Text key={index}>
            {line}
            {index === lines.length - 1 && cursorVisible ? '▍' : ''}
          </Text>
        ))}
      </Box>
      <Box paddingX={1}>
        <Text color={theme.blue}>model: {modelName}</Text>
        <Box flexGrow={1} />
        <Text dimColor>{timeStr}</Text>
      </Box>
    </Box>
  );
}

import React, { useEffect, useState } from 'react';
import { Box, Text } from 'ink';
import type { SlashCommand } from '../types';

export function InputFooter({
  value,
  menuOpen,
  menuIndex,
  commands,
}: {
  value: string;
  menuOpen: boolean;
  menuIndex: number;
  commands: SlashCommand[];
}) {
  const [cursorVisible, setCursorVisible] = useState(true);

  useEffect(() => {
    const timer = setInterval(() => setCursorVisible((current) => !current), 500);
    return () => clearInterval(timer);
  }, []);

  const lines = value.split('\n');

  return (
    <Box flexDirection="column" flexShrink={0}>
      {menuOpen ? (
        <Box position="absolute" bottom={1} flexDirection="column" paddingX={1}>
          {commands.map((command, index) => (
            <Text key={command.name} color={index === menuIndex ? 'cyan' : 'gray'}>
              {index === menuIndex ? '▸ ' : '  '}
              {command.name}
              <Text dimColor>  {command.desc}</Text>
            </Text>
          ))}
        </Box>
      ) : null}
      <Box paddingX={1}>
        <Text color="gray">&gt; </Text>
        {lines.map((line, index) => (
          <Text key={index}>
            {line}
            {index === lines.length - 1 && cursorVisible ? '▍' : ''}
          </Text>
        ))}
      </Box>
    </Box>
  );
}

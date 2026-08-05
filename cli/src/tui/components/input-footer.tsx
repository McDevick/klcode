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
        <Box
          position="absolute"
          bottom={5}
          borderStyle="round"
          borderColor="gray"
          backgroundColor="#313244"
          flexDirection="column"
          paddingX={1}
        >
          {commands.map((command, index) => (
            <Box key={command.name} backgroundColor={index === menuIndex ? 'cyan' : undefined}>
              <Text color={index === menuIndex ? 'black' : 'cyan'}>{command.name}</Text>
              <Text color={index === menuIndex ? 'black' : 'gray'}>  {command.desc}</Text>
            </Box>
          ))}
        </Box>
      ) : null}
      <Box
        height={5}
        borderStyle="round"
        borderColor="gray"
        paddingX={1}
        flexDirection="column"
      >
        {lines.map((line, index) => (
          <Text key={index}>
            {line}
            {index === lines.length - 1 && cursorVisible ? '|' : ''}
          </Text>
        ))}
      </Box>
    </Box>
  );
}

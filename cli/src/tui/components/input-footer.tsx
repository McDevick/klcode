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

  // 浮层最多显示 MAX_VISIBLE 行；选中项始终在窗口内，超出部分滚动查看
  const MAX_VISIBLE = 6;
  const windowStart = Math.max(
    0,
    Math.min(menuIndex - MAX_VISIBLE + 1, commands.length - MAX_VISIBLE),
  );
  const visibleCommands = commands.slice(windowStart, windowStart + MAX_VISIBLE);

  return (
    <Box flexDirection="column" flexShrink={0}>
      {menuOpen ? (
        <Box position="absolute" bottom={1} flexDirection="column" paddingX={1}>
          {visibleCommands.map((command, index) => {
            const absoluteIndex = windowStart + index;
            return (
              <Text key={command.name} color={absoluteIndex === menuIndex ? 'cyan' : 'gray'}>
                {absoluteIndex === menuIndex ? '▸ ' : '  '}
                {command.name}
                <Text dimColor>  {command.desc}</Text>
              </Text>
            );
          })}
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

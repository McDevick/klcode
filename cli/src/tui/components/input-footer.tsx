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

  // 浮层显示全部命令；命令超出窗口时滚动，选中项始终在窗口内
  const MAX_VISIBLE = 9;
  const windowStart = Math.max(
    0,
    Math.min(menuIndex - MAX_VISIBLE + 1, commands.length - MAX_VISIBLE),
  );
  const visibleCommands = commands.slice(windowStart, windowStart + MAX_VISIBLE);
  const hasMoreAbove = windowStart > 0;
  const hasMoreBelow = windowStart + MAX_VISIBLE < commands.length;

  return (
    <Box flexDirection="column" flexShrink={0}>
      {menuOpen ? (
        <Box position="absolute" bottom={1} flexDirection="column" paddingX={1}>
          {hasMoreAbove ? <Text dimColor>▲ 更多</Text> : null}
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
          {hasMoreBelow ? <Text dimColor>▼ 更多</Text> : null}
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

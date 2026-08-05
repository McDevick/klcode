import React, { useEffect, useState } from 'react';
import { Box, Text } from 'ink';
import type { SlashCommand } from '../types';
import { theme } from '../theme';

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

  // 命令面板：固定高度窗口 + 竖向滚动条；命令超出窗口时滚动，选中项始终在窗口内
  const MAX_VISIBLE = 8;
  const windowStart = Math.max(
    0,
    Math.min(menuIndex - MAX_VISIBLE + 1, commands.length - MAX_VISIBLE),
  );
  const visibleCommands = commands.slice(windowStart, windowStart + MAX_VISIBLE);
  const hasScroll = commands.length > MAX_VISIBLE;
  const thumbTop = hasScroll
    ? Math.round((windowStart / (commands.length - MAX_VISIBLE)) * (MAX_VISIBLE - 1))
    : 0;

  return (
    <Box flexDirection="column" flexShrink={0}>
      {menuOpen ? (
        <Box
          position="absolute"
          bottom={1}
          borderStyle="round"
          borderColor={theme.surfaceAlt}
          backgroundColor={theme.surface}
          flexDirection="row"
          paddingX={1}
        >
          <Box flexDirection="column">
            {visibleCommands.map((command, index) => {
              const absoluteIndex = windowStart + index;
              const selected = absoluteIndex === menuIndex;
              return (
                <Text key={command.name} color={selected ? theme.teal : theme.text}>
                  {selected ? '▸ ' : '  '}
                  {command.name}
                  <Text dimColor>  {command.desc}</Text>
                </Text>
              );
            })}
            {Array.from({ length: Math.max(0, MAX_VISIBLE - visibleCommands.length) }).map(
              (_, index) => (
                <Text key={`pad-${index}`}> </Text>
              ),
            )}
          </Box>
          {hasScroll ? (
            <Box flexDirection="column" paddingLeft={1}>
              {Array.from({ length: MAX_VISIBLE }).map((_, index) => (
                <Text key={index} color={index === thumbTop ? theme.teal : theme.textDim}>
                  {index === thumbTop ? '█' : '│'}
                </Text>
              ))}
            </Box>
          ) : null}
        </Box>
      ) : null}
      <Box paddingX={1}>
        <Box
          backgroundColor={theme.surface}
          borderStyle="round"
          borderColor={theme.surfaceAlt}
          paddingX={1}
          flexDirection="column"
        >
          <Text color={theme.teal}>&gt; </Text>
          {lines.map((line, index) => (
            <Text key={index}>
              {line}
              {index === lines.length - 1 && cursorVisible ? '▍' : ''}
            </Text>
          ))}
        </Box>
      </Box>
    </Box>
  );
}

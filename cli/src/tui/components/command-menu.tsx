import React from 'react';
import { Box, Text } from 'ink';
import type { SlashCommand } from '../types';
import { theme } from '../theme';

const MAX_VISIBLE = 8;

export function CommandMenu({
  commands,
  menuIndex,
}: {
  commands: SlashCommand[];
  menuIndex: number;
}) {
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
    <Box flexDirection="row" width="100%" backgroundColor={theme.surface} paddingX={1}>
      <Box flexDirection="column" flexGrow={1}>
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
  );
}

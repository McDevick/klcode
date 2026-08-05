import React, { useEffect, useState } from 'react';
import { Box, Text } from 'ink';
import type { RunningTask, ToolCall } from '../types';
import { padTag } from './messages';
import { theme } from '../theme';

function ToolTreeItem({ tool, isLast }: { tool: ToolCall; isLast: boolean }) {
  const connector = isLast ? '└─ ' : '├─ ';
  const summary = tool.summary.length > 60 ? `${tool.summary.slice(0, 60)}…` : tool.summary;
  const summaryColor = tool.summary.startsWith('error') ? theme.red : theme.textDim;
  return (
    <Text>
      <Text color={theme.textDim}>{connector}</Text>
      <Text color={theme.blue}>{tool.name}</Text>
      <Text color={theme.textDim}> → </Text>
      <Text color={summaryColor}>{summary}</Text>
    </Text>
  );
}

export function StatusCard({ running }: { running: RunningTask }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setElapsed(Math.max(0, (Date.now() - running.startedAt) / 1000));
    }, 100);
    return () => clearInterval(timer);
  }, [running.startedAt]);

  return (
    <Box paddingX={1} flexDirection="column">
      <Box>
        <Text bold color={theme.purple}>
          {padTag('[Agent]')}:{' '}
        </Text>
        <Text color={theme.purple}>thinking {elapsed.toFixed(1)} sec</Text>
        <Text dimColor>
          {' '}
          [{running.steps} steps]
        </Text>
      </Box>
      {running.toolCalls.length > 0 ? (
        <Box flexDirection="column" paddingLeft={3}>
          {running.toolCalls.map((tool, index) => (
            <ToolTreeItem
              key={`${tool.name}-${index}`}
              tool={tool}
              isLast={index === running.toolCalls.length - 1}
            />
          ))}
        </Box>
      ) : null}
    </Box>
  );
}

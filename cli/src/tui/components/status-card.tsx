import React, { useEffect, useState } from 'react';
import { Box, Text } from 'ink';
import { Spinner } from '@inkjs/ui';
import type { RunningTask } from '../types';
import { theme } from '../theme';

export function StatusCard({ running }: { running: RunningTask }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setElapsed(Math.max(0, Math.floor((Date.now() - running.startedAt) / 1000)));
    }, 500);
    return () => clearInterval(timer);
  }, [running.startedAt]);

  return (
    <Box paddingX={1}>
      <Box
        borderStyle="round"
        borderColor={theme.purple}
        backgroundColor={theme.surface}
        paddingX={1}
        flexDirection="column"
      >
        <Box>
          <Spinner type="dots" />
          <Text color={theme.purple}> 正在执行推理...</Text>
          <Text dimColor>
            {' '}
            [{elapsed}s] [{running.tokensUsed}/{running.maxTokens} tokens]
          </Text>
        </Box>
        {running.toolCalls.length > 0 ? (
          <Box flexDirection="column">
            {running.toolCalls.map((tool, index) => (
              <Box key={`${tool.name}-${index}`} flexDirection="column">
                <Text color={theme.teal}>▸ {tool.name}</Text>
                <Text dimColor>  {tool.args}</Text>
                <Text color={theme.green}>  → {tool.summary}</Text>
              </Box>
            ))}
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}

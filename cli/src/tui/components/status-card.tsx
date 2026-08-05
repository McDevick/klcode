import React, { useEffect, useState } from 'react';
import { Box, Text } from 'ink';
import { Spinner } from '@inkjs/ui';
import type { RunningTask } from '../types';

export function StatusCard({ running }: { running: RunningTask }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setElapsed(Math.max(0, Math.floor((Date.now() - running.startedAt) / 1000)));
    }, 500);
    return () => clearInterval(timer);
  }, [running.startedAt]);

  return (
    <Box flexDirection="column" paddingX={1}>
      <Box>
        <Spinner type="dots" />
        <Text color="cyan"> 正在执行推理...</Text>
        <Text dimColor>
          {' '}
          [{elapsed}s] [{running.tokensUsed}/{running.maxTokens} tokens]
        </Text>
      </Box>
      {running.toolCalls.length > 0 ? (
        <Box flexDirection="column">
          {running.toolCalls.map((tool, index) => (
            <Box key={`${tool.name}-${index}`} flexDirection="column">
              <Text color="cyan">▸ {tool.name}</Text>
              <Text dimColor>  {tool.args}</Text>
              <Text color="green">  → {tool.summary}</Text>
            </Box>
          ))}
        </Box>
      ) : null}
    </Box>
  );
}

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
    <Box borderStyle="double" borderColor="yellow" flexDirection="column" paddingX={1}>
      <Box>
        <Spinner type="dots" />
        <Text> 正在执行推理...</Text>
      </Box>
      <Box justifyContent="flex-end">
        <Text>
          ⏱️ 耗时: {elapsed}s 🪙 Tokens: {running.tokensUsed}/{running.maxTokens}
        </Text>
      </Box>
      {running.toolCalls.length > 0 ? (
        <Box flexDirection="column">
          {running.toolCalls.map((tool, index) => (
            <Box key={`${tool.name}-${index}`} flexDirection="column">
              <Text color="cyan">▸ {tool.name}</Text>
              <Text dimColor>  args: {tool.args}</Text>
              <Text color="green">  → {tool.summary}</Text>
            </Box>
          ))}
        </Box>
      ) : null}
    </Box>
  );
}

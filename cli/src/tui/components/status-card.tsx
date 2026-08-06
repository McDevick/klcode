import React, { useEffect, useState } from 'react';
import { Box, Text } from 'ink';
import type { RunningTask } from '../types';
import { padTag } from './messages';
import { theme } from '../theme';

// 任务运行中的状态卡：thinking 计时 + 已完成工具调用数。
// 工具调用明细不在这里（任务结束后会消失），而是作为消息流里的
// ToolCallLine 常驻，任务完成后仍可滚动回顾。
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
          [{running.steps} 次工具调用]
        </Text>
      </Box>
    </Box>
  );
}

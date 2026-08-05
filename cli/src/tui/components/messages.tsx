import React from 'react';
import { Box, Text, useStdout } from 'ink';
import type { ChatMessage, RunningTask } from '../types';
import { StatusCard } from './status-card';
import { MarkdownRenderer } from './markdown';
import { theme } from '../theme';

// 标签等宽使 [user]/[agent] 的方括号两侧对齐，文字在方括号内近似居中
export const TAG_WIDTH = 7;
export function padTag(tag: string): string {
  return tag.padEnd(TAG_WIDTH, ' ');
}

export function UserBubble({ content }: { content: string }) {
  return (
    <Box width="100%" flexDirection="row">
      <Box backgroundColor={theme.userBg} paddingX={1} width="100%">
        <Text bold color={theme.yellow}>
          {padTag('[User ]')}:{' '}
        </Text>
        <Text>{content}</Text>
      </Box>
    </Box>
  );
}

export function AgentBubble({ content, kind }: { content: string; kind: ChatMessage['kind'] }) {
  const prefix = (
    <Text bold color={theme.purple}>
      {padTag('[Agent]')}:{' '}
    </Text>
  );
  if (kind === 'error') {
    return (
      <Box paddingX={1}>
        {prefix}
        <Text color={theme.red}>✗ {content}</Text>
      </Box>
    );
  }
  if (kind === 'info') {
    return (
      <Box paddingX={1}>
        {prefix}
        <Text color={theme.textDim}>{content}</Text>
      </Box>
    );
  }
  if (kind === 'done') {
    return (
      <Box paddingX={1}>
        {prefix}
        <Text color={theme.green}>✓ {content}</Text>
      </Box>
    );
  }
  return (
    <Box paddingX={1}>
      {prefix}
      <MarkdownRenderer text={content} />
    </Box>
  );
}

export function Messages({
  messages,
  running,
  offset,
}: {
  messages: ChatMessage[];
  running: RunningTask | null;
  offset: number;
}) {
  // offset 是"隐藏最新 N 条"；滚动到最早时至少保留 1 条，避免对话完全消失
  // 窗口滚动：offset 是"从底部上移的行数"，窗口随滚动上移显示更早的对话，
  // 消息少时滚动窗口覆盖全部，滚到最早至少保留 1 条（不会整个对话消失）。
  const { stdout } = useStdout();
  const rows = stdout.rows ?? 24;
  const visibleCount = Math.max(1, rows - 6); // 减 header/输入框/状态栏等固定区域
  const end = Math.max(1, messages.length - offset);
  const start = Math.max(0, end - visibleCount);
  const visible = messages.slice(start, end);
  return (
    <Box flexGrow={1} flexDirection="column" paddingY={1}>
      {visible.map((message) => (
        <Box key={message.id} paddingY={1}>
          {message.role === 'user' ? (
            <UserBubble content={message.content} />
          ) : (
            <AgentBubble content={message.content} kind={message.kind} />
          )}
        </Box>
      ))}
      {running !== null ? (
        <Box paddingY={1}>
          <StatusCard running={running} />
        </Box>
      ) : null}
    </Box>
  );
}

import React, { useEffect, useRef, useState } from 'react';
import { Box, Text, type DOMElement } from 'ink';
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

// 工具调用行：[Tool]: run_command("python -m pytest") → ✓ exit 0 · 3 passed
// 结果状态用 ✓/✗ 着色，参数和摘要灰显，工具名保留原名（蓝色）
export function ToolCallLine({ tool }: { tool: NonNullable<ChatMessage['tool']> }) {
  const callText = tool.args ? `${tool.name}(${tool.args})` : tool.name;
  const summary = tool.summary.length > 120 ? `${tool.summary.slice(0, 120)}…` : tool.summary;
  const failureLabel = tool.ok ? '' : 'error: ';
  const cleanSummary = tool.ok ? summary : summary.replace(/^error:\s*/i, '');
  const marker = tool.ok ? '✓' : '✗';
  const markerColor = tool.ok ? theme.green : theme.red;
  return (
    <Box paddingX={1} flexDirection="column">
      <Text bold color={theme.blue}>[Tool]: {callText}</Text>
      {tool.taskItems ? (
        <Box paddingLeft={3} flexDirection="column">
          <Box flexDirection="row">
            <Text color={theme.textDim}>→ </Text>
            <Text color={markerColor}>{marker} </Text>
          </Box>
          {tool.taskItems.map((item, index) => (
            <Text
              key={`${item.title}-${index}`}
              color={item.done ? theme.green : theme.textDim}
              strikethrough={item.done}
            >
              {item.done ? '[✓] ' : '[ ] '}
              {item.title}
            </Text>
          ))}
        </Box>
      ) : (
        <Box paddingLeft={3}>
          <Text color={theme.textDim}>→ </Text>
          <Text color={markerColor}>{marker} </Text>
          <Text color={theme.textDim}>{failureLabel}{cleanSummary}</Text>
        </Box>
      )}
    </Box>
  );
}

export function Messages({
  messages,
  running,
  scrollTop,
  viewportRows,
  onScrollTopChange,
}: {
  messages: ChatMessage[];
  running: RunningTask | null;
  scrollTop: number;
  viewportRows: number;
  onScrollTopChange: React.Dispatch<React.SetStateAction<number>>;
}) {
  const contentRef = useRef<DOMElement | null>(null);
  const [contentHeight, setContentHeight] = useState(0);

  useEffect(() => {
    const node = contentRef.current;
    setContentHeight(node?.yogaNode?.getComputedHeight() ?? 0);
  }, [messages, running]);

  useEffect(() => {
    const maxScrollTop = Math.max(0, contentHeight - viewportRows);
    onScrollTopChange((current) => Math.min(current, maxScrollTop));
  }, [contentHeight, onScrollTopChange, viewportRows]);

  const effectiveScrollTop = Math.min(
    scrollTop,
    Math.max(0, contentHeight - viewportRows),
  );
  const top = -(Math.max(0, contentHeight - viewportRows) - effectiveScrollTop);

  return (
    <Box flexGrow={1} flexDirection="column">
      <Box
        height={viewportRows}
        flexDirection="column"
        overflowY="hidden"
        width="100%"
      >
        <Box
          ref={contentRef}
          position="absolute"
          top={top}
          left={0}
          width="100%"
          flexDirection="column"
        >
          {messages.map((message) => (
            <Box key={message.id}>
              {message.role === 'user' ? (
                <UserBubble content={message.content} />
              ) : message.kind === 'tool' && message.tool !== undefined ? (
                <ToolCallLine tool={message.tool} />
              ) : (
                <AgentBubble content={message.content} kind={message.kind} />
              )}
            </Box>
          ))}
          {running !== null ? (
            <Box>
              <StatusCard running={running} />
            </Box>
          ) : null}
        </Box>
      </Box>
    </Box>
  );
}

import React from 'react';
import { Box, Text } from 'ink';
import type { ChatMessage, RunningTask } from '../types';
import { StatusCard } from './status-card';
import { MarkdownRenderer } from './markdown';

export function UserBubble({ content }: { content: string }) {
  return (
    <Box paddingX={1}>
      <Text color="green">❯ </Text>
      <Text>{content}</Text>
    </Box>
  );
}

export function AgentBubble({ content, kind }: { content: string; kind: ChatMessage['kind'] }) {
  if (kind === 'error') {
    return (
      <Box paddingX={1}>
        <Text color="red">✗ {content}</Text>
      </Box>
    );
  }
  if (kind === 'info') {
    return (
      <Box paddingX={1}>
        <Text color="gray">ℹ {content}</Text>
      </Box>
    );
  }
  if (kind === 'done') {
    return (
      <Box paddingX={1}>
        <Text color="green">✓ {content}</Text>
      </Box>
    );
  }
  return (
    <Box paddingX={1} flexDirection="column">
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
  const visible = offset === 0 ? messages : messages.slice(0, Math.max(0, messages.length - offset));
  return (
    <Box flexGrow={1} flexDirection="column" paddingY={1}>
      {visible.map((message) =>
        message.role === 'user' ? (
          <UserBubble key={message.id} content={message.content} />
        ) : (
          <AgentBubble key={message.id} content={message.content} kind={message.kind} />
        ),
      )}
      {running !== null ? <StatusCard running={running} /> : null}
    </Box>
  );
}

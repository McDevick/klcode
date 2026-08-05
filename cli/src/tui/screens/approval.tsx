import React from 'react';
import { Box, Text } from 'ink';
import { DEFAULT_BASE_URL } from '../../api/client';
import { readDaemonToken } from '../../api/daemon-token';

export type ApprovalDecision = 'approve' | 'reject' | 'abort';

export function sendApprovalDecision(
  decision: ApprovalDecision,
  actionId: string,
  taskId: string,
  baseUrl: string = DEFAULT_BASE_URL,
  tokenPath?: string,
): void {
  const base = baseUrl.replace(/\/+$/, '');
  const token = readDaemonToken(tokenPath);
  const query = token ? `?token=${encodeURIComponent(token)}` : '';
  const socket = new WebSocket(`${base}/ws/tasks/${encodeURIComponent(taskId)}${query}`);
  socket.addEventListener('open', () => {
    socket.send(JSON.stringify({ event: decision, action_id: actionId }));
    socket.close();
  });
}

export function ApprovalPanel({
  tool,
  command,
  level,
}: {
  tool: string;
  command: string;
  level?: string;
}) {
  return (
    <Box flexDirection="column">
      <Text>
        requires approval{level ? ` (${level})` : ''}: {tool} {command}
      </Text>
      <Text>[a]pprove [r]eject [m]odify [x]bort</Text>
    </Box>
  );
}

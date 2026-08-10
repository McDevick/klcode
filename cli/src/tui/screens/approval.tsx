import React, { useEffect, useState } from 'react';
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
  deadline,
}: {
  tool: string;
  command: string;
  level?: string;
  deadline: number;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const remaining = Math.max(0, Math.ceil((deadline - now) / 1000));
  const minutes = Math.floor(remaining / 60);
  const seconds = String(remaining % 60).padStart(2, '0');

  return (
    <Box flexDirection="column">
      <Text>
        requires approval{level ? ` (${level})` : ''}: {tool} {command}
      </Text>
      <Text>剩余 {minutes}:{seconds}</Text>
      <Text>[a]pprove [r]eject [x]bort</Text>
    </Box>
  );
}

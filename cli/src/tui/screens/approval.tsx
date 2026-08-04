import React from 'react';
import { Box, Text, useInput } from 'ink';
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
  onApprove,
  onReject,
  onModify,
  onAbort,
  active = false,
  taskId,
  actionId,
  baseUrl,
  sendDecision,
}: {
  tool: string;
  command: string;
  onApprove?: () => void;
  onReject?: () => void;
  onModify?: () => void;
  onAbort?: () => void;
  active?: boolean;
  taskId?: string;
  actionId?: string;
  baseUrl?: string;
  sendDecision?: (decision: ApprovalDecision, actionId: string, taskId: string) => void;
}) {
  const send = (decision: ApprovalDecision) => {
    if (!actionId || !taskId) return;
    if (sendDecision) {
      sendDecision(decision, actionId, taskId);
    } else {
      sendApprovalDecision(decision, actionId, taskId, baseUrl);
    }
  };

  useInput(
    (input) => {
      if (input === 'a') {
        onApprove?.();
        send('approve');
      } else if (input === 'r') {
        onReject?.();
        send('reject');
      } else if (input === 'x') {
        onAbort?.();
        send('abort');
      } else if (input === 'm') {
        onModify?.();
      }
    },
    { isActive: active },
  );

  return (
    <Box flexDirection="column">
      <Text>
        requires approval: {tool} {command}
      </Text>
      <Text>[a]pprove [r]eject [m]odify</Text>
      <Text>[x]bort</Text>
    </Box>
  );
}

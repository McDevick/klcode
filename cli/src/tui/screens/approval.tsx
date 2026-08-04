import React from 'react';
import { Box, Text, useInput } from 'ink';

export function ApprovalPanel({
  tool,
  command,
  onApprove,
  onReject,
  onModify,
  active = false,
}: {
  tool: string;
  command: string;
  onApprove?: () => void;
  onReject?: () => void;
  onModify?: () => void;
  active?: boolean;
}) {
  useInput(
    (input) => {
      if (input === 'a') onApprove?.();
      else if (input === 'r') onReject?.();
      else if (input === 'm') onModify?.();
    },
    { isActive: active },
  );

  return (
    <Box flexDirection="column">
      <Text>
        requires approval: {tool} {command}
      </Text>
      <Text>[a]pprove [r]eject [m]odify</Text>
    </Box>
  );
}

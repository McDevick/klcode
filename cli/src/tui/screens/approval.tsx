import React from 'react';
import { Box, Text } from 'ink';

export function ApprovalPanel({
  tool,
  command,
  onApprove,
  onReject,
  onModify,
}: {
  tool: string;
  command: string;
  onApprove?: () => void;
  onReject?: () => void;
  onModify?: () => void;
}) {
  return (
    <Box flexDirection="column">
      <Text>
        requires approval: {tool} {command}
      </Text>
      <Text>[a]pprove [r]eject [m]odify</Text>
      {onApprove ? <Text>approve handler ready</Text> : null}
      {onReject ? <Text>reject handler ready</Text> : null}
      {onModify ? <Text>modify handler ready</Text> : null}
    </Box>
  );
}

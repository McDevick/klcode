import React from 'react';
import { Text } from 'ink';

export function ApprovalPanel({
  tool,
  command,
}: {
  tool: string;
  command: string;
}) {
  return (
    <Text>
      requires approval: {tool} {command}
    </Text>
  );
}

import React from 'react';
import { Box } from 'ink';
import { theme } from '../theme';

export function DockedPanel({
  children,
  borderColor = theme.border,
  borderBottom = false,
}: {
  children: React.ReactNode;
  borderColor?: string;
  borderBottom?: boolean;
}) {
  return (
    <Box
      flexShrink={0}
      flexDirection="column"
      width="100%"
      borderStyle="single"
      borderColor={borderColor}
      borderTop
      borderBottom={borderBottom}
      borderLeft={false}
      borderRight={false}
    >
      {children}
    </Box>
  );
}

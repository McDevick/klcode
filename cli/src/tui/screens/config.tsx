import React from 'react';
import { Box, Text } from 'ink';

export function ConfigWizard() {
  return (
    <Box flexDirection="column">
      <Text>config wizard</Text>
      <Text>provider name:</Text>
      <Text>type:</Text>
      <Text>base url:</Text>
      <Text>model:</Text>
      <Text>api key: [hidden]</Text>
    </Box>
  );
}

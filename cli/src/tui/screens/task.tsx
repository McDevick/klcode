import React from 'react';
import { Text } from 'ink';

export function TaskInput({ value }: { value: string }) {
  return (
    <>
      <Text>task&gt; {value}</Text>
    </>
  );
}

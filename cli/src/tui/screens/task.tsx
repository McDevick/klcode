import React, { useState } from 'react';
import { Text, useInput } from 'ink';

export function TaskInput({ onSubmit }: { onSubmit: (value: string) => void }) {
  const [value, setValue] = useState('');

  useInput((input, key) => {
    if (key.return) {
      onSubmit(value);
      setValue('');
      return;
    }

    if (key.backspace || key.delete) {
      setValue((current) => current.slice(0, -1));
      return;
    }

    setValue((current) => current + input);
  });

  return (
    <>
      <Text>task&gt; {value}</Text>
    </>
  );
}

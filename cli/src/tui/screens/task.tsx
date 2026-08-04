import React, { useRef, useState } from 'react';
import { Text, useInput } from 'ink';

export function TaskInput({
  onSubmit,
  active = true,
}: {
  onSubmit: (value: string) => void;
  active?: boolean;
}) {
  const [value, setValue] = useState('');
  const valueRef = useRef('');

  useInput((input, key) => {
    if (!active) return;
    if (key.return) {
      onSubmit(valueRef.current);
      valueRef.current = '';
      setValue('');
      return;
    }

    if (key.backspace || key.delete) {
      valueRef.current = valueRef.current.slice(0, -1);
      setValue((current) => current.slice(0, -1));
      return;
    }

    valueRef.current += input;
    setValue(valueRef.current);
  }, { isActive: active });

  return (
    <>
      <Text>task&gt; {value}</Text>
    </>
  );
}

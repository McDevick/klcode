import React, { useRef, useState } from 'react';
import { Box, Text, useInput } from 'ink';

export interface ConfigValues {
  providerName: string;
  type: string;
  baseUrl: string;
  model: string;
  apiKey: string;
}

export function ConfigWizard({ onSave }: { onSave?: (values: ConfigValues) => void }) {
  const [values, setValues] = useState<ConfigValues>({
    providerName: '',
    type: '',
    baseUrl: '',
    model: '',
    apiKey: '',
  });
  const [focus, setFocus] = useState(0);
  const valuesRef = useRef(values);
  const focusRef = useRef(focus);

  const fields: Array<{ key: keyof ConfigValues; label: string }> = [
    { key: 'providerName', label: 'provider name' },
    { key: 'type', label: 'type' },
    { key: 'baseUrl', label: 'base url' },
    { key: 'model', label: 'model' },
    { key: 'apiKey', label: 'api key' },
  ];

  const updateField = (key: keyof ConfigValues, value: string) => {
    valuesRef.current = { ...valuesRef.current, [key]: value };
    setValues(valuesRef.current);
  };

  useInput((input, key) => {
    if (key.tab || key.return) {
      if (focusRef.current === fields.length - 1 && key.return) {
        onSave?.(valuesRef.current);
      } else {
        focusRef.current = (focusRef.current + 1) % fields.length;
        setFocus(focusRef.current);
      }
      return;
    }
    const currentKey = fields[focusRef.current].key;
    if (key.backspace || key.delete) {
      updateField(currentKey, valuesRef.current[currentKey].slice(0, -1));
    } else {
      updateField(currentKey, valuesRef.current[currentKey] + input);
    }
  });

  return (
    <Box flexDirection="column">
      <Text>config wizard</Text>
      {fields.map((field, index) => (
        <Text key={field.key}>
          {field.label}:{' '}
          {field.key === 'apiKey'
            ? values[field.key] ? '*'.repeat(values[field.key].length) : '[hidden]'
            : values[field.key]}
          {index === focus ? ' <' : ''}
        </Text>
      ))}
    </Box>
  );
}

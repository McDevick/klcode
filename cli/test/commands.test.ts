import { expect, test } from 'vitest';
import { ConfigCommand } from '../src/commands/config';

test('config command exposes wizard name', () => {
  expect(ConfigCommand.name).toBe('config');
});

test('config command exposes wizard alias and run', () => {
  expect(ConfigCommand.aliases).toContain('/cfg');
  expect(ConfigCommand.run([])).toContain('config wizard');
});

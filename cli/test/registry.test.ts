import { expect, test } from 'vitest';
import { CommandRegistry } from '../src/commands/registry';

test('registry resolves command and help', () => {
  const registry = new CommandRegistry();
  registry.register({ name: 'help', aliases: ['/h'], run: () => 'help text' });
  expect(registry.resolve('/h').name).toBe('help');
  expect(registry.help().includes('/help')).toBe(true);
});

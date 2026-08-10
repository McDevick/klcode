import { expect, test } from 'vitest';
import { CommandRegistry } from '../src/commands/registry';

test('registry resolves command and help', () => {
  const registry = new CommandRegistry();
  registry.register({ name: 'help', aliases: ['/h'], run: () => 'help text' });
  expect(registry.resolve('/h').name).toBe('help');
  expect(registry.help().includes('/help')).toBe(true);
});

test('registry normalizes leading slash, case, and whitespace', () => {
  const registry = new CommandRegistry();
  registry.register({ name: 'help', aliases: ['/h'], run: () => 'help text' });
  expect(registry.resolve('/HELP').name).toBe('help');
  expect(registry.resolve(' /help ').name).toBe('help');
  expect(registry.resolve('h').name).toBe('help');
});

test('registry throws on unknown and duplicate commands', () => {
  const registry = new CommandRegistry();
  registry.register({ name: 'help', aliases: ['/h'], run: () => 'help text' });
  expect(() => registry.resolve('/missing')).toThrow('unknown command');
  expect(() => registry.register({ name: 'Help', aliases: [], run: () => 'x' })).toThrow('duplicate command');
});

test('registry passes args to run', () => {
  const registry = new CommandRegistry();
  registry.register({ name: 'echo', aliases: [], run: (args) => args.join(' ') });
  const command = registry.resolve('/echo');
  expect(command.run(['a', 'b'])).toBe('a b');
});

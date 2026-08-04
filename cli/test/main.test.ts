import { expect, test } from 'vitest';
import { buildProgram, cliName } from '../src/main';

test('cli exposes package name', () => {
  expect(cliName()).toBe('kl-code');
});

test('commander exposes top-level commands', () => {
  const program = buildProgram();

  expect(program.name()).toBe('kl');
  const names = program.commands.map((command) => command.name());
  expect(names).toEqual(expect.arrayContaining(['init', 'run', 'server', 'config']));
});

test('commander commands define expected arguments', () => {
  const program = buildProgram();
  const run = program.commands.find((command) => command.name() === 'run');
  const server = program.commands.find((command) => command.name() === 'server');
  const config = program.commands.find((command) => command.name() === 'config');

  expect(run?.registeredArguments.map((argument) => argument.name())).toEqual(['task']);
  expect(server?.registeredArguments.map((argument) => argument.name())).toEqual(['action']);
  expect(config?.registeredArguments.map((argument) => argument.name())).toEqual([
    'area',
    'action',
    'args',
  ]);
});

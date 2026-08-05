import * as React from 'react';
import { Command } from 'commander';
import { render } from 'ink';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { ConfigCommand } from './commands/config';
import { InitCommand } from './commands/init';
import { RunCommand } from './commands/run';
import { ServerCommand } from './commands/server';
import { App } from './tui/app';

export function cliName(): string {
  return 'kl-code';
}

export function buildProgram(): Command {
  const program = new Command();
  program.name('kl').description('KL Code CLI');

  program.command('init').description('check local initialization state').action(async () => {
    console.log(await InitCommand.run());
  });

  program
    .command('run')
    .argument('<task>', 'task description')
    .description('create a one-off task')
    .action(async (task: string) => {
      console.log(await RunCommand.run([task]));
    });

  program
    .command('server')
    .argument('<action>', 'start|stop|status')
    .description('manage the local daemon')
    .action(async (action: string) => {
      console.log(await ServerCommand.run([action]));
    });

  program
    .command('config')
    .argument('<area>', 'provider or key')
    .argument('<action>', 'subcommand')
    .argument('[args...]', 'subcommand arguments')
    .description('manage providers and keys')
    .action(async (area: string, action: string, args: string[]) => {
      console.log(await ConfigCommand.run([area, action, ...args]));
    });

  program
    .command('tui')
    .description('launch the interactive TUI')
    .action(() => {
      render(React.createElement(App));
    });

  return program;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  buildProgram().parse(process.argv);
}

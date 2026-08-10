import * as React from 'react';
import { Command } from 'commander';
import { render } from 'ink';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { ApiClient, DEFAULT_BASE_URL } from './api/client';
import { autoStartDaemon, isConnectionError } from './api/daemon';
import { ConfigCommand } from './commands/config';
import { InitCommand } from './commands/init';
import { RunCommand } from './commands/run';
import { ServerCommand } from './commands/server';
import { App } from './tui/app';

export function cliName(): string {
  return 'kl-code';
}

export interface EnsureServerReadyOptions {
  client?: ApiClient;
  autoStart?: () => Promise<boolean>;
}

export async function ensureServerReady(
  options: EnsureServerReadyOptions = {},
): Promise<boolean> {
  const client = options.client ?? new ApiClient({ baseUrl: DEFAULT_BASE_URL });
  const autoStart = options.autoStart ?? (() => autoStartDaemon({ client }));
  try {
    await client.health();
    return true;
  } catch (error) {
    if (!isConnectionError(error)) {
      return false;
    }
    console.log('正在检查/安装并启动服务端...');
    const started = await autoStart();
    if (!started) {
      console.error(
        '服务端启动失败。请先运行 kl init，或手动执行: python -m pip install kl-server && kl server start',
      );
      return false;
    }
    return true;
  }
}

export function buildProgram(): Command {
  const program = new Command();
  program.name('kl').description('KL Code CLI');

  program.command('init').description('check local initialization state').action(async () => {
    console.log(await InitCommand.run([]));
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
    .action(async () => {
      const ready = await ensureServerReady();
      if (!ready) {
        process.exitCode = 1;
        return;
      }
      // 备用屏幕缓冲区（alt screen）：终端滚动条不滚动 TUI 的重绘历史。
      // 对话滚动由 TUI 内部处理（方向键/PageUp/PageDown，滚轮需 /mouse 开启）。
      // 默认不启用鼠标追踪（SGR）：鼠标拖动选择/复制随时可用；
      // /mouse 开启追踪后滚轮内部滚动可用，复制改用 Shift+拖动。
      process.stdout.write('[?1049h');
      process.on('exit', () => {
        process.stdout.write('[?1000l[?1006l');
        process.stdout.write('[?2004l');
        process.stdout.write('[?1049l');
      });
      render(React.createElement(App));
    });

  return program;
}

const entryPath = process.argv[1] ? resolve(process.argv[1]) : '';
if (entryPath && entryPath.toLowerCase().endsWith('main.js')) {
  buildProgram().parse(process.argv);
}
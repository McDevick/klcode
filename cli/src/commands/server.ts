import { execFileSync, spawn } from 'node:child_process';
import {
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { homedir } from 'node:os';
import { delimiter, dirname, join } from 'node:path';
import { ApiClient, DEFAULT_BASE_URL } from '../api/client';
import { SERVER_VERSION } from '../server-version';

export interface ServerProcessLike {
  pid?: number;
  unref?: () => void;
}

export interface ServerSpawnOptions {
  cwd?: string;
  stdio?: 'ignore';
  detached?: boolean;
  env?: NodeJS.ProcessEnv;
}

export interface DaemonRecord {
  pid: number;
  source: 'manual' | 'auto';
  started_at: string;
}

export interface DaemonStatus {
  source: string;
  running_tasks: number;
  ws_connections: number;
}

export type ServerSpawnImpl = (
  command: string,
  args: readonly string[],
  options: ServerSpawnOptions,
) => ServerProcessLike;

export interface ServerCommandOptions {
  baseUrl?: string;
  tokenPath?: string;
  pidPath?: string;
  daemonPath?: string;
  spawnImpl?: ServerSpawnImpl;
  killImpl?: (pid: number) => boolean;
  probeImpl?: (pid: number) => boolean;
  statusImpl?: () => Promise<DaemonStatus>;
  pythonResolver?: () => Promise<string | null>;
  source?: 'manual' | 'auto';
}

const PYTHON_CANDIDATES = ['python', 'python3', 'py'];

function serverRoots(): string[] {
  return [join(process.cwd(), 'server'), join(process.cwd(), '..', 'server')].filter(
    existsSync,
  );
}

function probeEnv(): NodeJS.ProcessEnv {
  const roots = serverRoots();
  if (roots.length === 0) {
    return process.env;
  }
  return {
    ...process.env,
    PYTHONPATH: [roots.join(delimiter), process.env.PYTHONPATH]
      .filter(Boolean)
      .join(delimiter),
  };
}

function venvPythonName(): string {
  return process.platform === 'win32' ? 'Scripts\\python.exe' : 'bin/python';
}

function globalKlDir(): string {
  return join(homedir(), '.kl');
}

function globalVenvPython(): string {
  return join(globalKlDir(), 'venv', venvPythonName());
}

function canImportServer(python: string, env: NodeJS.ProcessEnv): boolean {
  try {
    execFileSync(python, ['-c', 'import uvicorn, fastapi, kl_server'], {
      stdio: 'pipe',
      env,
    });
    return true;
  } catch {
    return false;
  }
}

export async function resolveGlobalVenvPython(
  env: NodeJS.ProcessEnv = probeEnv(),
  python: string = globalVenvPython(),
): Promise<string | null> {
  return canImportServer(python, env) ? python : null;
}

export async function resolvePathPython(
  env: NodeJS.ProcessEnv = probeEnv(),
): Promise<string | null> {
  // PATH 候选：解析真实可执行路径。Windows 的 py launcher 会另起 python.exe 后退出，
  // 直接 spawn launcher 会导致 pid 指向已退出的进程且服务端生命周期不稳定。
  for (const candidate of PYTHON_CANDIDATES) {
    try {
      const probe = execFileSync(
        candidate,
        ['-c', 'import sys; import uvicorn, fastapi, kl_server; print(sys.executable)'],
        { encoding: 'utf8', stdio: 'pipe', env },
      );
      const resolved = probe.trim();
      return resolved.length > 0 ? resolved : candidate;
    } catch {
      // try the next candidate
    }
  }
  return null;
}

function findPythonExecutable(env: NodeJS.ProcessEnv = probeEnv()): string | null {
  for (const candidate of PYTHON_CANDIDATES) {
    try {
      const probe = execFileSync(
        candidate,
        ['-c', 'import sys; print(sys.executable)'],
        { encoding: 'utf8', stdio: 'pipe', env },
      );
      const resolved = probe.trim();
      return resolved.length > 0 ? resolved : candidate;
    } catch {
      // try the next candidate
    }
  }
  return null;
}

function discoverServerDir(): string | null {
  return serverRoots()[0] ?? null;
}

async function confirmBootstrap(version: string): Promise<boolean> {
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    return true;
  }
  const { createInterface } = await import('node:readline/promises');
  const readline = createInterface({ input: process.stdin, output: process.stdout });
  try {
    const answer = await readline.question(
      `首次运行将创建全局环境 ~/.kl/venv 并安装 kl-server（版本 ${version}），是否继续？[Y/n] `,
    );
    return answer.trim() === '' || /^y/i.test(answer.trim());
  } finally {
    readline.close();
  }
}

export interface BootstrapGlobalVenvOptions {
  klDir?: string;
  python?: string | null;
  serverDir?: string | null;
  version?: string;
  env?: NodeJS.ProcessEnv;
  confirm?: () => Promise<boolean>;
  canImport?: (python: string, env: NodeJS.ProcessEnv) => boolean;
  execFileSyncImpl?: (
    command: string,
    args: readonly string[],
    options?: { env?: NodeJS.ProcessEnv; stdio?: 'pipe' | 'ignore'; encoding?: string; cwd?: string },
  ) => string | void;
}

export async function bootstrapGlobalVenv(
  options: BootstrapGlobalVenvOptions = {},
): Promise<string | null> {
  const env = options.env ?? probeEnv();
  const python =
    options.python !== undefined ? options.python : findPythonExecutable(env);
  if (python === null) {
    return null;
  }
  const version = options.version ?? SERVER_VERSION;
  const confirm = options.confirm ?? (() => confirmBootstrap(version));
  if (!(await confirm())) {
    return null;
  }
  const klDir = options.klDir ?? globalKlDir();
  const venv = join(klDir, 'venv');
  const venvPython = join(venv, venvPythonName());
  const execImpl = options.execFileSyncImpl ?? execFileSync;
  try {
    execImpl(python, ['-m', 'venv', venv], { stdio: 'pipe', env });
    const serverDir =
      options.serverDir !== undefined ? options.serverDir : discoverServerDir();
    if (serverDir !== null) {
      execImpl(venvPython, ['-m', 'pip', 'install', '-e', serverDir], {
        stdio: 'pipe',
        env,
      });
    } else {
      execImpl(venvPython, ['-m', 'pip', 'install', `kl-server==${version}`], {
        stdio: 'pipe',
        env,
      });
    }
  } catch {
    return null;
  }
  const canImport = options.canImport ?? canImportServer;
  return canImport(venvPython, env) ? venvPython : null;
}

export async function defaultPythonResolver(): Promise<string | null> {
  const env = probeEnv();
  const globalVenv = await resolveGlobalVenvPython(env);
  if (globalVenv !== null) {
    return globalVenv;
  }
  const pathPython = await resolvePathPython(env);
  if (pathPython !== null) {
    return pathPython;
  }
  return bootstrapGlobalVenv({ env });
}

function defaultPidPath(): string {
  return join(homedir(), '.kl', 'daemon.pid');
}

function defaultDaemonPath(): string {
  return join(homedir(), '.kl', 'daemon.json');
}

function readPid(pidPath: string): number | undefined {
  if (!existsSync(pidPath)) {
    return undefined;
  }
  const parsed = Number(readFileSync(pidPath, 'utf8').trim());
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function writePid(pidPath: string, pid: number): void {
  mkdirSync(dirname(pidPath), { recursive: true });
  writeFileSync(pidPath, String(pid));
}

function removePid(pidPath: string): void {
  rmSync(pidPath, { force: true });
}

function readDaemon(daemonPath: string): DaemonRecord | undefined {
  if (!existsSync(daemonPath)) {
    return undefined;
  }
  try {
    const parsed = JSON.parse(readFileSync(daemonPath, 'utf8')) as Partial<DaemonRecord>;
    if (
      typeof parsed.pid !== 'number' ||
      !Number.isInteger(parsed.pid) ||
      parsed.pid <= 0 ||
      (parsed.source !== 'manual' && parsed.source !== 'auto')
    ) {
      return undefined;
    }
    return {
      pid: parsed.pid,
      source: parsed.source,
      started_at:
        typeof parsed.started_at === 'string'
          ? parsed.started_at
          : new Date().toISOString(),
    };
  } catch {
    return undefined;
  }
}

function writeDaemon(daemonPath: string, record: DaemonRecord): void {
  mkdirSync(dirname(daemonPath), { recursive: true });
  writeFileSync(daemonPath, JSON.stringify(record, null, 2));
}

function removeDaemon(daemonPath: string): void {
  rmSync(daemonPath, { force: true });
}

function isPidAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === 'EPERM';
  }
}

export const ServerCommand = {
  name: 'server',
  run: async (args: string[], options: ServerCommandOptions = {}): Promise<string> => {
    const action = args[0];
    const pidPath = options.pidPath ?? defaultPidPath();
    const daemonPath = options.daemonPath ?? defaultDaemonPath();
    const baseUrl = options.baseUrl ?? DEFAULT_BASE_URL;
    const client = new ApiClient({ baseUrl, tokenPath: options.tokenPath });

    switch (action) {
      case 'start': {
        const existingPid = readPid(pidPath);
        if (existingPid !== undefined) {
          const daemon = readDaemon(daemonPath);
          const alive = (options.probeImpl ?? isPidAlive)(existingPid);
          if (!alive) {
            removePid(pidPath);
            removeDaemon(daemonPath);
          } else {
            const source = daemon?.source ?? 'manual';
            if (source === 'manual') {
              return `server already running (pid ${existingPid})`;
            }
            const statusImpl =
              options.statusImpl ?? (() => client.daemonStatus());
            let status: DaemonStatus;
            try {
              status = await statusImpl();
            } catch {
              status = { source, running_tasks: 0, ws_connections: 0 };
            }
            if (status.running_tasks > 0) {
              return (
                `cannot start manual server while auto daemon runs a task ` +
                `(${status.running_tasks} running); stop or abort it first`
              );
            }
            const killImpl =
              options.killImpl ??
              ((candidatePid: number) => {
                try {
                  process.kill(candidatePid);
                  return true;
                } catch {
                  return false;
                }
              });
            killImpl(existingPid);
            removePid(pidPath);
            removeDaemon(daemonPath);
          }
        }
        const resolvePython = options.pythonResolver ?? defaultPythonResolver;
        const python = await resolvePython();
        if (python === null) {
          return (
            'server start failed: no usable python found.\n' +
            'a) install Python (>= 3.11) and retry\n' +
            'b) manually run: pip install kl-server\n' +
            'c) start with a project venv: <venv>/bin/python -m uvicorn kl_server.main:app --host 127.0.0.1 --port 8700'
          );
        }
        const spawnImpl = (options.spawnImpl ?? spawn) as ServerSpawnImpl;
        const pythonPath = serverRoots().join(delimiter);
        const env = pythonPath
          ? {
              ...process.env,
              PYTHONPATH: [pythonPath, process.env.PYTHONPATH].filter(Boolean).join(delimiter),
              KL_DAEMON_SOURCE: options.source ?? 'manual',
            }
          : {
              ...process.env,
              KL_DAEMON_SOURCE: options.source ?? 'manual',
            };
        const child = spawnImpl(
          python,
          [
            '-m',
            'uvicorn',
            'kl_server.main:app',
            '--host',
            '127.0.0.1',
            '--port',
            '8700',
            // Ctrl+C 时优雅关闭有上限：默认 None 会无限等待活动连接（如挂着的
            // WebSocket），导致进程成僵尸并占住 8700 端口
            '--timeout-graceful-shutdown',
            '3',
          ],
          {
            cwd: process.cwd(),
            stdio: 'ignore',
            detached: true,
            env,
          },
        );
        child.unref?.();
        if (child.pid !== undefined) {
          writePid(pidPath, child.pid);
          writeDaemon(daemonPath, {
            pid: child.pid,
            source: options.source ?? 'manual',
            started_at: new Date().toISOString(),
          });
        }
        return `server started (pid ${child.pid ?? 'unknown'})`;
      }
      case 'stop': {
        const pid = readPid(pidPath);
        if (pid === undefined) {
          return 'server not running';
        }
        const killImpl =
          options.killImpl ??
          ((candidatePid: number) => {
            try {
              process.kill(candidatePid);
              return true;
            } catch {
              return false;
            }
          });
        const stopped = killImpl(pid);
        if (!stopped) {
          return `server stop failed (pid ${pid})`;
        }
        removePid(pidPath);
        removeDaemon(daemonPath);
        return 'server stopped';
      }
      case 'status': {
        const pid = readPid(pidPath);
        const daemon = readDaemon(daemonPath);
        try {
          await client.health();
          const source = daemon?.source ?? 'manual';
          return pid === undefined
            ? 'server running'
            : `server running (pid ${pid}, source ${source})`;
        } catch {
          return pid === undefined
            ? 'server not running'
            : `server not responding (stale pid ${pid})`;
        }
      }
      default:
        return 'usage: kl server start|stop|status';
    }
  },
};

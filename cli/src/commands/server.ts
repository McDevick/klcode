import { execFileSync, spawn } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { delimiter, dirname, join } from 'node:path';
import { ApiClient, DEFAULT_BASE_URL } from '../api/client';

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

export type ServerSpawnImpl = (
  command: string,
  args: readonly string[],
  options: ServerSpawnOptions,
) => ServerProcessLike;

export interface ServerCommandOptions {
  baseUrl?: string;
  tokenPath?: string;
  pidPath?: string;
  spawnImpl?: ServerSpawnImpl;
  killImpl?: (pid: number) => boolean;
  pythonResolver?: () => Promise<string | null>;
}

const PYTHON_CANDIDATES = ['python', 'python3', 'py'];

async function defaultPythonResolver(): Promise<string | null> {
  for (const candidate of PYTHON_CANDIDATES) {
    try {
      execFileSync(candidate, ['-c', 'import uvicorn, fastapi, kl_server'], {
        stdio: 'pipe',
      });
      return candidate;
    } catch {
      // try the next candidate
    }
  }
  return null;
}

function defaultPidPath(): string {
  return join(homedir(), '.kl', 'daemon.pid');
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

export const ServerCommand = {
  name: 'server',
  run: async (args: string[], options: ServerCommandOptions = {}): Promise<string> => {
    const action = args[0];
    const pidPath = options.pidPath ?? defaultPidPath();
    const baseUrl = options.baseUrl ?? DEFAULT_BASE_URL;
    const client = new ApiClient({ baseUrl, tokenPath: options.tokenPath });

    switch (action) {
      case 'start': {
        const existingPid = readPid(pidPath);
        if (existingPid !== undefined) {
          return `server already running (pid ${existingPid})`;
        }
        const resolvePython = options.pythonResolver ?? defaultPythonResolver;
        const python = await resolvePython();
        if (python === null) {
          return 'server start failed: no usable python found (needs uvicorn, fastapi and kl_server; use the project venv python)';
        }
        const spawnImpl = (options.spawnImpl ?? spawn) as ServerSpawnImpl;
        const serverRoots = [join(process.cwd(), 'server'), join(process.cwd(), '..', 'server')].filter(
          existsSync,
        );
        const pythonPath = serverRoots.length > 0 ? serverRoots.join(delimiter) : undefined;
        const env = pythonPath
          ? {
              ...process.env,
              PYTHONPATH: [pythonPath, process.env.PYTHONPATH].filter(Boolean).join(delimiter),
            }
          : process.env;
        const child = spawnImpl(
          python,
          ['-m', 'uvicorn', 'kl_server.main:app', '--host', '127.0.0.1', '--port', '8700'],
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
        return 'server stopped';
      }
      case 'status': {
        const pid = readPid(pidPath);
        try {
          await client.health();
          return pid === undefined ? 'server running' : `server running (pid ${pid})`;
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

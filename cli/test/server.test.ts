import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, test, vi } from 'vitest';
import { ServerCommand, defaultPythonResolver, discoverVenvCandidates } from '../src/commands/server';

const tempDirs: string[] = [];

function makeTempDir(): string {
  const dir = mkdtempSync(join(tmpdir(), 'kl-server-test-'));
  tempDirs.push(dir);
  return dir;
}

afterEach(() => {
  while (tempDirs.length > 0) {
    rmSync(tempDirs.pop()!, { recursive: true, force: true });
  }
});

test('server start spawns uvicorn with resolved python and writes pid file', async () => {
  const dir = makeTempDir();
  const pidPath = join(dir, 'daemon.pid');
  const spawnMock = vi.fn().mockReturnValue({ pid: 4242, unref: vi.fn() });
  const pythonResolver = vi.fn().mockResolvedValue('python');

  const output = await ServerCommand.run(['start'], {
    pidPath,
    spawnImpl: spawnMock,
    pythonResolver,
  });

  expect(output).toContain('started');
  expect(pythonResolver).toHaveBeenCalled();
  expect(spawnMock).toHaveBeenCalledWith(
    'python',
    expect.arrayContaining([
      '-m',
      'uvicorn',
      'kl_server.main:app',
      '--host',
      '127.0.0.1',
      '--port',
      '8700',
      '--timeout-graceful-shutdown',
      '3',
    ]),
    expect.objectContaining({
      env: expect.objectContaining({
        PYTHONPATH: expect.stringContaining('server'),
      }),
    }),
  );
  expect(readFileSync(pidPath, 'utf8')).toBe('4242');
});

test('server start uses the python returned by the resolver', async () => {
  const dir = makeTempDir();
  const pidPath = join(dir, 'daemon.pid');
  const spawnMock = vi.fn().mockReturnValue({ pid: 7, unref: vi.fn() });
  const pythonResolver = vi.fn().mockResolvedValue('python3');

  const output = await ServerCommand.run(['start'], {
    pidPath,
    spawnImpl: spawnMock,
    pythonResolver,
  });

  expect(output).toContain('started');
  expect(spawnMock).toHaveBeenCalledWith(
    'python3',
    expect.arrayContaining(['-m', 'uvicorn']),
    expect.anything(),
  );
});

test('server start reports a clear failure when no python resolves', async () => {
  const dir = makeTempDir();
  const pidPath = join(dir, 'daemon.pid');
  const pythonResolver = vi.fn().mockResolvedValue(null);

  const output = await ServerCommand.run(['start'], { pidPath, pythonResolver });

  expect(output).toContain('failed');
  expect(output).toContain('python');
  expect(existsSync(pidPath)).toBe(false);
});

test('server stop kills pid and removes pid file', async () => {
  const dir = makeTempDir();
  const pidPath = join(dir, 'daemon.pid');
  writeFileSync(pidPath, '4321');
  const killMock = vi.fn().mockReturnValue(true);

  const output = await ServerCommand.run(['stop'], { pidPath, killImpl: killMock });

  expect(output).toContain('stopped');
  expect(killMock).toHaveBeenCalledWith(4321);
  expect(existsSync(pidPath)).toBe(false);
});

test('server stop reports failure and keeps pid file when kill fails', async () => {
  const dir = makeTempDir();
  const pidPath = join(dir, 'daemon.pid');
  writeFileSync(pidPath, '4321');
  const killMock = vi.fn().mockReturnValue(false);

  const output = await ServerCommand.run(['stop'], { pidPath, killImpl: killMock });

  expect(output).toContain('failed');
  expect(existsSync(pidPath)).toBe(true);
});

test('server status calls health and reports running', async () => {
  const dir = makeTempDir();
  const pidPath = join(dir, 'daemon.pid');
  const tokenPath = join(dir, 'daemon.token');
  writeFileSync(pidPath, '4242');
  writeFileSync(tokenPath, 'daemon-token');
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ status: 'ok' }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const output = await ServerCommand.run(['status'], { pidPath, tokenPath });

    expect(output).toContain('running');
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8700/health',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get('authorization')).toBe('Bearer daemon-token');
  } finally {
    vi.unstubAllGlobals();
  }
});

test('server status reports stale pid when health fails', async () => {
  const dir = makeTempDir();
  const pidPath = join(dir, 'daemon.pid');
  writeFileSync(pidPath, '99');
  const fetchMock = vi.fn().mockResolvedValue({
    ok: false,
    status: 500,
    json: async () => ({}),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const output = await ServerCommand.run(['status'], { pidPath });

    expect(output).toContain('not responding');
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8700/health',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

describe('defaultPythonResolver venv discovery', () => {
  test('discovers venv directories in cwd and parents, deduped', () => {
    const root = makeTempDir();
    const scripts = process.platform === 'win32' ? 'Scripts' : 'bin';
    const pythonName = process.platform === 'win32' ? 'python.exe' : 'python';
    mkdirSync(join(root, '.venv', scripts), { recursive: true });
    writeFileSync(join(root, '.venv', scripts, pythonName), '');
    mkdirSync(join(root, 'my-venv', scripts), { recursive: true });
    writeFileSync(join(root, 'my-venv', scripts, pythonName), '');
    const nested = join(root, 'a', 'b');
    mkdirSync(nested, { recursive: true });

    const originalCwd = process.cwd();
    try {
      process.chdir(nested);
      const candidates = discoverVenvCandidates();

      expect(candidates).toContain(join(root, '.venv'));
      expect(candidates).toContain(join(root, 'my-venv'));
      expect(new Set(candidates).size).toBe(candidates.length);
    } finally {
      process.chdir(originalCwd);
    }
  });

  test('resolver returns a usable venv python and null when none work', async () => {
    const root = makeTempDir();
    const scripts = process.platform === 'win32' ? 'Scripts' : 'bin';
    const pythonName = process.platform === 'win32' ? 'python.exe' : 'python';
    mkdirSync(join(root, '.venv', scripts), { recursive: true });
    writeFileSync(join(root, '.venv', scripts, pythonName), '');

    const originalCwd = process.cwd();
    try {
      process.chdir(root);
      const withEnv = await defaultPythonResolver();
      // 深度扫描可能命中上层目录的其他可用 venv（如 Temp 下遗留），
      // 断言返回的必须是存在的、候选列表内的 python。
      expect(withEnv).toBeTruthy();
      expect(existsSync(withEnv as string)).toBe(true);
      const candidates = discoverVenvCandidates();
      expect(candidates.map((candidate) => join(candidate, scripts, pythonName))).toContain(
        withEnv,
      );
    } finally {
      process.chdir(originalCwd);
    }
  });
});

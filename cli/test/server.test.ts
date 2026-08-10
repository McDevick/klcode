import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, test, vi } from 'vitest';
import { ServerCommand, bootstrapGlobalVenv, resolveGlobalVenvPython } from '../src/commands/server';

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

test('server start writes daemon.json and manual source env', async () => {
  const dir = makeTempDir();
  const pidPath = join(dir, 'daemon.pid');
  const daemonPath = join(dir, 'daemon.json');
  const spawnMock = vi.fn().mockReturnValue({ pid: 55, unref: vi.fn() });
  const pythonResolver = vi.fn().mockResolvedValue('python');

  const output = await ServerCommand.run(['start'], {
    pidPath,
    daemonPath,
    spawnImpl: spawnMock,
    pythonResolver,
  });

  expect(output).toContain('started');
  expect(JSON.parse(readFileSync(daemonPath, 'utf8'))).toMatchObject({
    pid: 55,
    source: 'manual',
  });
  const env = spawnMock.mock.calls[0][2].env;
  expect(env.KL_DAEMON_SOURCE).toBe('manual');
});

test('server start cleans stale pid and daemon record', async () => {
  const dir = makeTempDir();
  const pidPath = join(dir, 'daemon.pid');
  const daemonPath = join(dir, 'daemon.json');
  writeFileSync(pidPath, '4242');
  writeFileSync(daemonPath, JSON.stringify({ pid: 4242, source: 'auto', started_at: 'x' }));
  const spawnMock = vi.fn().mockReturnValue({ pid: 7, unref: vi.fn() });

  const output = await ServerCommand.run(['start'], {
    pidPath,
    daemonPath,
    spawnImpl: spawnMock,
    pythonResolver: vi.fn().mockResolvedValue('python'),
    probeImpl: () => false,
  });

  expect(output).toContain('started');
  expect(readFileSync(pidPath, 'utf8')).toBe('7');
  expect(JSON.parse(readFileSync(daemonPath, 'utf8')).source).toBe('manual');
});

test('server start reports already running for live manual daemon', async () => {
  const dir = makeTempDir();
  const pidPath = join(dir, 'daemon.pid');
  const daemonPath = join(dir, 'daemon.json');
  writeFileSync(pidPath, '4242');
  writeFileSync(daemonPath, JSON.stringify({ pid: 4242, source: 'manual', started_at: 'x' }));
  const spawnMock = vi.fn();

  const output = await ServerCommand.run(['start'], {
    pidPath,
    daemonPath,
    spawnImpl: spawnMock,
    pythonResolver: vi.fn().mockResolvedValue('python'),
    probeImpl: () => true,
  });

  expect(output).toContain('already running');
  expect(spawnMock).not.toHaveBeenCalled();
});

test('server start refuses takeover while auto daemon runs tasks', async () => {
  const dir = makeTempDir();
  const pidPath = join(dir, 'daemon.pid');
  const daemonPath = join(dir, 'daemon.json');
  writeFileSync(pidPath, '4242');
  writeFileSync(daemonPath, JSON.stringify({ pid: 4242, source: 'auto', started_at: 'x' }));
  const spawnMock = vi.fn();

  const output = await ServerCommand.run(['start'], {
    pidPath,
    daemonPath,
    spawnImpl: spawnMock,
    pythonResolver: vi.fn().mockResolvedValue('python'),
    probeImpl: () => true,
    statusImpl: async () => ({ source: 'auto', running_tasks: 1, ws_connections: 0 }),
  });

  expect(output).toContain('cannot start manual server');
  expect(spawnMock).not.toHaveBeenCalled();
});

test('server start takes over idle auto daemon', async () => {
  const dir = makeTempDir();
  const pidPath = join(dir, 'daemon.pid');
  const daemonPath = join(dir, 'daemon.json');
  writeFileSync(pidPath, '4242');
  writeFileSync(daemonPath, JSON.stringify({ pid: 4242, source: 'auto', started_at: 'x' }));
  const killMock = vi.fn().mockReturnValue(true);
  const spawnMock = vi.fn().mockReturnValue({ pid: 9, unref: vi.fn() });

  const output = await ServerCommand.run(['start'], {
    pidPath,
    daemonPath,
    spawnImpl: spawnMock,
    killImpl: killMock,
    pythonResolver: vi.fn().mockResolvedValue('python'),
    probeImpl: () => true,
    statusImpl: async () => ({ source: 'auto', running_tasks: 0, ws_connections: 0 }),
  });

  expect(output).toContain('started');
  expect(killMock).toHaveBeenCalledWith(4242);
  expect(JSON.parse(readFileSync(daemonPath, 'utf8')).source).toBe('manual');
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

describe('global venv resolution', () => {
  test('resolveGlobalVenvPython returns null when python cannot import server', async () => {
    const fakeVenvPython = join(makeTempDir(), 'venv', 'missing.py');
    expect(await resolveGlobalVenvPython(process.env, fakeVenvPython)).toBeNull();
  });
});

describe('bootstrapGlobalVenv', () => {
  const scripts = process.platform === 'win32' ? 'Scripts' : 'bin';
  const pythonName = process.platform === 'win32' ? 'python.exe' : 'python';

  test('creates global venv and installs pinned server version', async () => {
    const klDir = makeTempDir();
    const calls: string[] = [];
    const runMock = vi.fn().mockImplementation(async (command: string, args: string[]) => {
      calls.push(`${command} ${args.join(' ')}`);
      return { code: 0, timedOut: false, stdout: '', stderr: '' };
    });

    const python = await bootstrapGlobalVenv({
      klDir,
      python: 'python',
      serverDir: null,
      version: '1.2.3',
      canImport: () => true,
      runProcess: runMock,
    });

    const expected = join(klDir, 'venv', scripts, pythonName);
    expect(python).toBe(expected);
    expect(calls[0]).toContain('python -m venv');
    expect(calls[1]).toContain(`pip install kl-server==1.2.3`);
  });

  test('installs editable source server when server dir exists', async () => {
    const klDir = makeTempDir();
    const serverDir = makeTempDir();
    const calls: string[] = [];
    const runMock = vi.fn().mockImplementation(async (command: string, args: string[]) => {
      calls.push(`${command} ${args.join(' ')}`);
      return { code: 0, timedOut: false, stdout: '', stderr: '' };
    });

    await bootstrapGlobalVenv({
      klDir,
      python: 'python',
      serverDir,
      canImport: () => true,
      runProcess: runMock,
    });

    expect(calls[1]).toContain(`pip install -e ${serverDir}`);
  });

  test('returns null when user declines bootstrap', async () => {
    const klDir = makeTempDir();

    const python = await bootstrapGlobalVenv({
      klDir,
      python: 'python',
      confirm: async () => false,
    });

    expect(python).toBeNull();
  });

  test('returns null when no python executable is available', async () => {
    expect(await bootstrapGlobalVenv({ python: null })).toBeNull();
  });
});

  test('returns null and removes venv when install fails', async () => {
    const klDir = makeTempDir();
    const venvDir = join(klDir, 'venv');
    mkdirSync(venvDir, { recursive: true });
    writeFileSync(join(venvDir, 'marker'), 'x');
    const runMock = vi
      .fn()
      .mockResolvedValueOnce({ code: 0, timedOut: false, stdout: '', stderr: '' })
      .mockResolvedValueOnce({ code: 1, timedOut: false, stdout: '', stderr: '' });

    const python = await bootstrapGlobalVenv({
      klDir,
      python: 'python',
      runProcess: runMock,
    });

    expect(python).toBeNull();
    expect(existsSync(venvDir)).toBe(false);
  });

  test('returns null and removes venv when install times out', async () => {
    const klDir = makeTempDir();
    const venvDir = join(klDir, 'venv');
    mkdirSync(venvDir, { recursive: true });
    const runMock = vi
      .fn()
      .mockResolvedValueOnce({ code: 0, timedOut: false, stdout: '', stderr: '' })
      .mockResolvedValueOnce({ code: -1, timedOut: true, stdout: '', stderr: '' });

    const python = await bootstrapGlobalVenv({
      klDir,
      python: 'python',
      runProcess: runMock,
    });

    expect(python).toBeNull();
    expect(existsSync(venvDir)).toBe(false);
  });
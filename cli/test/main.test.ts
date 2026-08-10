import { expect, test, vi } from 'vitest';
import { buildProgram, cliName } from '../src/main';

test('cli exposes package name', () => {
  expect(cliName()).toBe('kl-code');
});

test('commander exposes top-level commands', () => {
  const program = buildProgram();

  expect(program.name()).toBe('kl');
  const names = program.commands.map((command) => command.name());
  expect(names).toEqual(expect.arrayContaining(['init', 'run', 'server', 'config', 'tui']));
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

import { ApiClient, DEFAULT_BASE_URL } from '../src/api/client';
import { ensureServerReady } from '../src/main';

test('ensureServerReady returns true when server is already healthy', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ status: 'ok' }),
  });
  vi.stubGlobal('fetch', fetchMock);
  const autoStart = vi.fn();
  try {
    const ready = await ensureServerReady({
      client: new ApiClient({ baseUrl: DEFAULT_BASE_URL }),
      autoStart,
    });

    expect(ready).toBe(true);
    expect(autoStart).not.toHaveBeenCalled();
  } finally {
    vi.unstubAllGlobals();
  }
});

test('ensureServerReady auto-starts server on connection error', async () => {
  const fetchMock = vi.fn().mockRejectedValue(new TypeError('fetch failed'));
  vi.stubGlobal('fetch', fetchMock);
  const autoStart = vi.fn().mockResolvedValue(true);
  try {
    const ready = await ensureServerReady({
      client: new ApiClient({ baseUrl: DEFAULT_BASE_URL }),
      autoStart,
    });

    expect(ready).toBe(true);
    expect(autoStart).toHaveBeenCalledTimes(1);
  } finally {
    vi.unstubAllGlobals();
  }
});

test('ensureServerReady returns false when auto-start fails', async () => {
  const fetchMock = vi.fn().mockRejectedValue(new TypeError('fetch failed'));
  vi.stubGlobal('fetch', fetchMock);
  const autoStart = vi.fn().mockResolvedValue(false);
  try {
    const ready = await ensureServerReady({
      client: new ApiClient({ baseUrl: DEFAULT_BASE_URL }),
      autoStart,
    });

    expect(ready).toBe(false);
    expect(autoStart).toHaveBeenCalledTimes(1);
  } finally {
    vi.unstubAllGlobals();
  }
});
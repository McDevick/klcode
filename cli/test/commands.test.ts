import { expect, test, vi } from 'vitest';
import { ConfigCommand } from '../src/commands/config';

test('config command exposes wizard name', () => {
  expect(ConfigCommand.name).toBe('config');
});

test('config command exposes wizard alias and run', () => {
  expect(ConfigCommand.aliases).toContain('/cfg');
  expect(ConfigCommand.run([])).toContain('config wizard');
});

import { SessionCommand } from '../src/commands/session';
import { ApiClient } from '../src/api/client';

test('session command exposes subcommands', () => {
  expect(SessionCommand.aliases).toContain('/sessions');
});

test('session command lists sessions', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => [{ id: 's1' }],
  });
  vi.stubGlobal('fetch', fetchMock);
  const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700' });
  const sessions = await client.listSessions();
  expect(sessions).toEqual([{ id: 's1' }]);
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:8700/api/v1/sessions',
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
  vi.unstubAllGlobals();
});

test('session command opens session by id', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ id: 's1' }),
  });
  vi.stubGlobal('fetch', fetchMock);
  const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700' });
  const session = await client.getSession('s1');
  expect(session).toEqual({ id: 's1' });
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:8700/api/v1/sessions/s1',
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
  vi.unstubAllGlobals();
});

test('session command creates session', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ id: 's1' }),
  });
  vi.stubGlobal('fetch', fetchMock);
  const result = await SessionCommand.run(['new', 'E:/repo']);
  expect(JSON.parse(result)).toEqual({ id: 's1' });
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:8700/api/v1/sessions',
    expect.objectContaining({ method: 'POST' }),
  );
  vi.unstubAllGlobals();
});

test('session command handles rename close and delete', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ id: 's1' }),
  });
  vi.stubGlobal('fetch', fetchMock);
  await SessionCommand.run(['rename', 's1', 'new name']);
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:8700/api/v1/sessions/s1',
    expect.objectContaining({ method: 'PATCH', body: expect.stringContaining('new name') }),
  );
  await SessionCommand.run(['close', 's1']);
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:8700/api/v1/sessions/s1/close',
    expect.objectContaining({ method: 'POST' }),
  );
  await SessionCommand.run(['delete', 's1']);
  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:8700/api/v1/sessions/s1',
    expect.objectContaining({ method: 'DELETE' }),
  );
  vi.unstubAllGlobals();
});

test('api client surfaces fetch failures', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    }),
  );
  const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700' });
  await expect(client.getSession('s1')).rejects.toThrow('request failed: 500');
  vi.unstubAllGlobals();
});

test('session command handles 204 delete response', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => {
        throw new Error('no body');
      },
    }),
  );
  const result = await SessionCommand.run(['delete', 's1']);
  expect(result).toBe('deleted');
  vi.unstubAllGlobals();
});

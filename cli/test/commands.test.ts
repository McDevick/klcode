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
  expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8700/api/v1/sessions');
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
  expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8700/api/v1/sessions/s1');
  vi.unstubAllGlobals();
});

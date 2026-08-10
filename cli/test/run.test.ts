import { expect, test, vi } from 'vitest';
import { DEFAULT_BASE_URL } from '../src/api/client';
import { RunCommand } from '../src/commands/run';

test('run command creates a session first then a task in that session', async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ id: 's1', workspace: process.cwd(), name: 'default', status: 'active' }),
    })
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        id: 't1',
        session_id: 's1',
        description: 'fix the bug',
        status: 'pending',
      }),
    });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const output = await RunCommand.run(['fix the bug']);

    expect(output).toContain('t1');
    expect(output).toContain('pending');
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      `${DEFAULT_BASE_URL}/api/v1/sessions`,
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"workspace"'),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      `${DEFAULT_BASE_URL}/api/v1/tasks`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ session_id: 's1', description: 'fix the bug' }),
      }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('run command with empty description shows usage', async () => {
  const output = await RunCommand.run(['']);

  expect(output).toContain('usage');
});

test('run command auto-starts daemon on connection error and retries', async () => {
  const fetchMock = vi
    .fn()
    .mockRejectedValueOnce(new TypeError('fetch failed'))
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ id: 's1', workspace: process.cwd(), name: 'default', status: 'active' }),
    })
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ id: 't1', session_id: 's1', description: 'fix', status: 'pending' }),
    });
  vi.stubGlobal('fetch', fetchMock);
  const serverStart = vi.fn().mockResolvedValue('server started (pid 123)');
  const healthCheck = vi.fn().mockResolvedValue(true);
  try {
    const output = await RunCommand.run(['fix'], {
      serverStart,
      healthCheck,
    });

    expect(serverStart).toHaveBeenCalledWith(['start']);
    expect(healthCheck).toHaveBeenCalledTimes(1);
    expect(output).toContain('t1');
  } finally {
    vi.unstubAllGlobals();
  }
});

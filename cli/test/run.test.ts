import { expect, test, vi } from 'vitest';
import { DEFAULT_BASE_URL } from '../src/api/client';
import { RunCommand } from '../src/commands/run';

test('run command creates task and reports id and status', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      id: 't1',
      session_id: 'default',
      description: 'fix the bug',
      status: 'pending',
    }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const output = await RunCommand.run(['fix the bug']);

    expect(output).toContain('t1');
    expect(output).toContain('pending');
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/tasks`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ session_id: 'default', description: 'fix the bug' }),
      }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

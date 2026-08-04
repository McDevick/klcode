import { expect, test, vi } from 'vitest';
import { DEFAULT_BASE_URL } from '../src/api/client';
import { InitCommand } from '../src/commands/init';

test('init command calls config check and returns setup guidance', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ status: 'ok', providers: ['mock'] }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const output = await InitCommand.run([]);

    expect(output).toContain('ok');
    expect(output).toContain('mock');
    expect(output).toContain('kl config');
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/config/check`,
      expect.objectContaining({ method: 'POST' }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

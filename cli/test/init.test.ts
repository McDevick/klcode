import { expect, test, vi } from 'vitest';
import { ApiClient, DEFAULT_BASE_URL } from '../src/api/client';
import { InitCommand } from '../src/commands/init';

const okResponse = {
  ok: true,
  status: 200,
  json: async () => ({ status: 'ok', providers: ['mock'] }),
};

test('init command calls config check and returns setup guidance', async () => {
  const fetchMock = vi.fn().mockResolvedValue(okResponse);
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

test('init auto-starts daemon on connection error and retries', async () => {
  const fetchMock = vi
    .fn()
    .mockRejectedValueOnce(new TypeError('fetch failed'))
    .mockResolvedValueOnce(okResponse)
    .mockResolvedValueOnce(okResponse);
  vi.stubGlobal('fetch', fetchMock);
  const serverStart = vi.fn().mockResolvedValue('server started (pid 123)');
  const healthCheck = vi.fn().mockResolvedValue(true);
  try {
    const output = await InitCommand.run([], {
      serverStart,
      healthCheck,
      client: new ApiClient({ baseUrl: DEFAULT_BASE_URL }),
    });

    expect(serverStart).toHaveBeenCalledWith(['start']);
    expect(healthCheck).toHaveBeenCalledTimes(1);
    expect(output).toContain('initialization status: ok');
  } finally {
    vi.unstubAllGlobals();
  }
});

test('init reports auto-start failure clearly', async () => {
  const fetchMock = vi.fn().mockRejectedValue(new TypeError('fetch failed'));
  vi.stubGlobal('fetch', fetchMock);
  const serverStart = vi
    .fn()
    .mockResolvedValue('server start failed: no usable python found (needs uvicorn, fastapi and kl_server; use the project venv python)');
  try {
    const output = await InitCommand.run([], {
      serverStart,
      client: new ApiClient({ baseUrl: DEFAULT_BASE_URL }),
    });

    expect(output).toContain('init failed: daemon not running and auto-start failed');
    expect(serverStart).toHaveBeenCalledWith(['start']);
  } finally {
    vi.unstubAllGlobals();
  }
});

test('init does not auto-start on http errors', async () => {
  const fetchMock = vi.fn().mockRejectedValue(new Error('request failed: 500'));
  vi.stubGlobal('fetch', fetchMock);
  const serverStart = vi.fn();
  try {
    await expect(
      InitCommand.run([], {
        serverStart,
        client: new ApiClient({ baseUrl: DEFAULT_BASE_URL }),
      }),
    ).rejects.toThrow('request failed: 500');
    expect(serverStart).not.toHaveBeenCalled();
  } finally {
    vi.unstubAllGlobals();
  }
});

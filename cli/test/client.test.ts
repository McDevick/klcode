import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { expect, test, vi } from 'vitest';
import { ApiClient } from '../src/api/client';

test('client builds task URL', () => {
  const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700' });
  expect(client.taskUrl('t1')).toBe('http://127.0.0.1:8700/api/v1/tasks/t1');
});

test('client trims trailing slash and encodes task id', () => {
  const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700/' });
  expect(client.taskUrl('a/b?c')).toBe('http://127.0.0.1:8700/api/v1/tasks/a%2Fb%3Fc');
});

test('client sends bearer token from token file', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'kl-client-token-'));
  const tokenPath = join(dir, 'daemon.token');
  writeFileSync(tokenPath, 'token-123\n');
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ id: 's1' }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700', tokenPath });
    await client.getSession('s1');
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get('authorization')).toBe('Bearer token-123');
  } finally {
    vi.unstubAllGlobals();
    rmSync(dir, { recursive: true, force: true });
  }
});

test('client runs a task via the run endpoint', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 202,
    json: async () => ({ status: 'running' }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700' });
    const result = await client.runTask('t1');

    expect(result).toEqual({ status: 'running' });
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8700/api/v1/tasks/t1/run',
      expect.objectContaining({ method: 'POST' }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('client controls task lifecycle via abort pause continue endpoints', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ status: 'ok' }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700' });

    await client.abortTask('t1');
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'http://127.0.0.1:8700/api/v1/tasks/t1/abort',
      expect.objectContaining({ method: 'POST' }),
    );

    await client.pauseTask('t1');
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://127.0.0.1:8700/api/v1/tasks/t1/pause',
      expect.objectContaining({ method: 'POST' }),
    );

    await client.continueTask('t1');
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      'http://127.0.0.1:8700/api/v1/tasks/t1/continue',
      expect.objectContaining({ method: 'POST' }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('client omits authorization when token file is missing', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'kl-client-no-token-'));
  const tokenPath = join(dir, 'missing-token');
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ id: 's1' }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700', tokenPath });
    await client.getSession('s1');
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.has('authorization')).toBe(false);
  } finally {
    vi.unstubAllGlobals();
    rmSync(dir, { recursive: true, force: true });
  }
});

test('client gets model config', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      provider: 'mock',
      model: 'mock-model',
      available: [{ provider: 'mock', model: 'mock-model', base_url: '' }],
    }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700' });
    const result = await client.getModelConfig();

    expect(result.provider).toBe('mock');
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8700/api/v1/config/model',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('client sets model config with provider and model', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ provider: 'deepseek', model: 'deepseek-chat', available: [] }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700' });
    await client.setModelConfig({ provider: 'deepseek', model: 'deepseek-chat' });

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ provider: 'deepseek', model: 'deepseek-chat' });
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8700/api/v1/config/model',
      expect.objectContaining({ method: 'POST' }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('client lists models', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => [{ provider: 'mock', model: 'mock-model', base_url: '' }],
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700' });
    const result = await client.listModels();

    expect(result[0]).toMatchObject({ provider: 'mock', model: 'mock-model' });
  } finally {
    vi.unstubAllGlobals();
  }
});

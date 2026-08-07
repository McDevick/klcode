import { expect, test, vi } from 'vitest';
import { DEFAULT_BASE_URL } from '../src/api/client';
import { ConfigCommand } from '../src/commands/config';

test('config command exposes wizard name', () => {
  expect(ConfigCommand.name).toBe('config');
});

test('config command exposes wizard alias and run', () => {
  expect(ConfigCommand.aliases).toContain('/cfg');
  expect(ConfigCommand.run([])).toContain('config wizard');
});

test('config provider add posts provider and returns provider', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      name: 'acme',
      type: 'openai-compatible',
      base_url: 'http://example.com/v1',
      default_model: 'model-x',
    }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const result = await ConfigCommand.run([
      'provider',
      'add',
      'acme',
      'openai-compatible',
      'http://example.com/v1',
      'model-x',
    ]);

    expect(JSON.parse(result)).toMatchObject({ name: 'acme' });
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/providers`,
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"name":"acme"'),
      }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('config provider list includes mock', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => [{ name: 'mock', type: 'mock' }],
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const result = await ConfigCommand.run(['provider', 'list']);

    expect(result).toContain('mock');
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/providers`,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('config provider test reports provider availability', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => [{ name: 'mock', type: 'mock' }],
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const result = await ConfigCommand.run(['provider', 'test']);

    expect(result).toContain('ok');
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/providers`,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('config key set never returns secret in output', async () => {
  const secret = 'sk-super-secret';
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ configured: true }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const result = await ConfigCommand.run(['key', 'set', 'openai', secret]);

    expect(result).toContain('configured');
    expect(result).not.toContain(secret);
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/keys/openai`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ secret }),
      }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('config key show returns only configured status', async () => {
  const secret = 'sk-super-secret';
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ configured: true }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const result = await ConfigCommand.run(['key', 'show', 'openai']);

    expect(result).toContain('configured');
    expect(result).not.toContain(secret);
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/keys/openai`,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('config key clear calls delete route', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ configured: false }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const result = await ConfigCommand.run(['key', 'clear', 'openai']);

    expect(result).toContain('configured');
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/keys/openai`,
      expect.objectContaining({ method: 'DELETE' }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('config key test calls status route', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ configured: true }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const result = await ConfigCommand.run(['key', 'test', 'openai']);

    expect(result).toContain('configured');
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/keys/openai`,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('config mcp list formats servers and tools', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => [
      {
        name: 'demo',
        url: 'http://localhost:9999',
        tools: [
          {
            name: 'mcp_demo_echo',
            remote_name: 'echo',
            description: 'echo text',
          },
        ],
      },
    ],
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const result = await ConfigCommand.run(['mcp', 'list']);

    expect(result).toContain('demo: url http://localhost:9999');
    expect(result).toContain('(1 tools)');
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/mcp`,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('config mcp add posts command server config', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      name: 'filesystem',
      command: 'npx',
      args: ['-y', '@modelcontextprotocol/server-filesystem'],
      tools: [],
    }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const result = await ConfigCommand.run([
      'mcp',
      'add',
      'filesystem',
      'command',
      'npx',
      '-y',
      '@modelcontextprotocol/server-filesystem',
    ]);

    expect(result).toContain('mcp server added: filesystem');
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/mcp`,
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"command":"npx"'),
      }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('config mcp remove calls delete route', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 204,
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const result = await ConfigCommand.run(['mcp', 'remove', 'demo']);

    expect(result).toContain('mcp server removed: demo');
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/mcp/demo`,
      expect.objectContaining({ method: 'DELETE' }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
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
  expect(result).toContain('会话已创建');
  expect(result).toContain('s1');
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
  expect(result).toBe('会话 s1 已删除');
  vi.unstubAllGlobals();
});

test('config model show returns current model', async () => {
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
    const result = await ConfigCommand.run(['model', 'show']);

    expect(result).toContain('mock-model');
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/config/model`,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('config model set posts provider and model', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ provider: 'deepseek', model: 'deepseek-chat', available: [] }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const result = await ConfigCommand.run(['model', 'set', 'deepseek', 'deepseek-chat']);

    expect(result).toContain('deepseek');
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/config/model`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ provider: 'deepseek', model: 'deepseek-chat' }),
      }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('config model set without model posts empty model', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ provider: 'deepseek', model: 'deepseek-chat', available: [] }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    await ConfigCommand.run(['model', 'set', 'deepseek']);

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ provider: 'deepseek', model: '' });
  } finally {
    vi.unstubAllGlobals();
  }
});

test('config model list shows available providers', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => [
      { provider: 'mock', model: 'mock-model', base_url: '' },
      { provider: 'deepseek', model: 'deepseek-chat', base_url: 'https://api.deepseek.com/v1' },
    ],
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const result = await ConfigCommand.run(['model', 'list']);

    expect(result).toContain('mock: mock-model');
    expect(result).toContain('deepseek: deepseek-chat');
  } finally {
    vi.unstubAllGlobals();
  }
});

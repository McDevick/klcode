import { expect, test, vi } from 'vitest';
import { render } from 'ink-testing-library';
import React from 'react';
import { TaskInput } from '../src/tui/screens/task';
import { ApprovalPanel } from '../src/tui/screens/approval';
import { App } from '../src/tui/app';
import { ConfigWizard } from '../src/tui/screens/config';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onmessage: ((event: { data: string }) => void) | null = null;
  sent: string[] = [];
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  addEventListener(event: string, callback: () => void) {
    if (event === 'open') {
      callback();
    }
  }
}

function stubWebSocket() {
  const original = globalThis.WebSocket;
  (globalThis as { WebSocket: unknown }).WebSocket = FakeWebSocket;
  return () => {
    (globalThis as { WebSocket: unknown }).WebSocket = original;
    FakeWebSocket.instances = [];
  };
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

test('task input renders prompt', () => {
  const { lastFrame } = render(<TaskInput onSubmit={() => {}} />);
  expect(lastFrame()).toContain('task>');
});

test('approval panel shows pending action', () => {
  const { lastFrame } = render(<ApprovalPanel tool="run_command" command="rm -rf /" />);
  expect(lastFrame()).toContain('requires approval');
  expect(lastFrame()).toContain('rm -rf /');
  expect(lastFrame()).toContain('[a]pprove [r]eject [m]odify');
});

test('app creates a session on start and submits tasks to the backend', async () => {
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
      json: async () => ({ id: 't1', session_id: 's1', description: 'hello', status: 'pending' }),
    })
    .mockResolvedValueOnce({ ok: true, status: 202, json: async () => ({ status: 'running' }) });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await sleep(30);
    stdin.write('hello');
    stdin.write('\r');
    await sleep(50);

    expect(lastFrame()).toContain('task t1 created');
    expect(lastFrame()).toContain('task running');
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'http://127.0.0.1:8700/api/v1/sessions',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://127.0.0.1:8700/api/v1/tasks',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      'http://127.0.0.1:8700/api/v1/tasks/t1/run',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(FakeWebSocket.instances.length).toBeGreaterThan(0);
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app shows approval panel from websocket event and sends decision', async () => {
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
      json: async () => ({ id: 't1', session_id: 's1', description: 'hello', status: 'pending' }),
    })
    .mockResolvedValueOnce({ ok: true, status: 202, json: async () => ({ status: 'running' }) });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await sleep(30);
    stdin.write('hello');
    stdin.write('\r');
    await sleep(50);

    const socket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    socket.onmessage?.({
      data: JSON.stringify({
        task_id: 't1',
        event: 'approval_request',
        action_id: 'a1',
        tool: 'run_command',
        args: { command: 'rm -rf /' },
        level: 'critical',
      }),
    });
    await sleep(30);
    expect(lastFrame()).toContain('requires approval');
    expect(lastFrame()).toContain('rm -rf /');

    stdin.write('a');
    await sleep(30);
    const decisionSocket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    expect(decisionSocket.sent.some((data) => data.includes('"approve"'))).toBe(true);
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('config wizard accepts fields and saves hidden key', async () => {
  const onSave = vi.fn();
  const { stdin, lastFrame, unmount } = render(<ConfigWizard onSave={onSave} />);
  stdin.write('acme');
  stdin.write('\t');
  stdin.write('custom');
  stdin.write('\t');
  stdin.write('http://example.com');
  stdin.write('\t');
  stdin.write('model-x');
  stdin.write('\t');
  stdin.write('secret');
  stdin.write('\r');
  await sleep(30);
  expect(lastFrame()).toContain('acme');
  expect(lastFrame()).toContain('http://example.com');
  expect(lastFrame()).toContain('model-x');
  expect(lastFrame()).toContain('******');
  expect(onSave).toHaveBeenCalledWith({
    providerName: 'acme',
    type: 'custom',
    baseUrl: 'http://example.com',
    model: 'model-x',
    apiKey: 'secret',
  });
  unmount();
});

test('app opens config wizard from /config', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ id: 's1', workspace: process.cwd(), name: 'default', status: 'active' }),
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await sleep(30);
    stdin.write('/config');
    stdin.write('\r');
    await sleep(20);
    expect(lastFrame()).toContain('config wizard');
    expect(lastFrame()).toContain('api key');
    stdin.write('acme');
    stdin.write('\t');
    stdin.write('custom');
    stdin.write('\t');
    stdin.write('http://example.com');
    stdin.write('\t');
    stdin.write('model-x');
    stdin.write('\t');
    stdin.write('secret');
    stdin.write('\r');
    await sleep(30);
    expect(lastFrame()).toContain('config wizard');
    expect(lastFrame()).not.toContain('requires approval');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app runs session command from slash input', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ id: 's1', workspace: process.cwd(), name: 'default', status: 'active' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [{ id: 's1' }],
      }),
  );
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await sleep(30);
    stdin.write('/sessions');
    stdin.write('\r');
    await sleep(30);
    expect(lastFrame()).toContain('"id":"s1"');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

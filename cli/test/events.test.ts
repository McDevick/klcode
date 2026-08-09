import { expect, test, vi } from 'vitest';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { connectDaemonPresence, connectTaskEvents, connectTaskEventsWithReconnect, type TaskEvent } from '../src/api/events';

test('connectTaskEvents parses valid events and ignores malformed ones', () => {
  const dir = mkdtempSync(join(tmpdir(), 'kl-events-no-token-'));
  const tokenPath = join(dir, 'missing.token');
  class FakeWebSocket {
    url: string;
    onmessage: ((event: { data: string }) => void) | null = null;

    constructor(url: string) {
      this.url = url;
    }
  }

  const original = globalThis.WebSocket;
  (globalThis as { WebSocket: unknown }).WebSocket = FakeWebSocket;

  const received: TaskEvent[] = [];
  const socket = connectTaskEvents('t1', (event) => received.push(event), {
    baseUrl: 'http://example.com/',
    tokenPath,
  }) as unknown as FakeWebSocket;

  try {
    expect(socket.url).toBe('http://example.com/ws/tasks/t1');
    socket.onmessage?.({ data: JSON.stringify({ task_id: 't1', event: 'ok' }) });
    socket.onmessage?.({ data: 'bad json' });
    socket.onmessage?.({ data: JSON.stringify({ task_id: 't1' }) });
    expect(received).toEqual([{ task_id: 't1', event: 'ok' }]);
  } finally {
    rmSync(dir, { recursive: true, force: true });
    (globalThis as { WebSocket: unknown }).WebSocket = original;
  }
});

test('connectDaemonPresence opens daemon websocket with token and close', () => {
  const dir = mkdtempSync(join(tmpdir(), 'kl-events-daemon-'));
  const tokenPath = join(dir, 'daemon.token');
  writeFileSync(tokenPath, 'token-789');
  class FakeDaemonWebSocket {
    url: string;
    close() {}
    onopen: (() => void) | null = null;

    constructor(url: string) {
      this.url = url;
    }
  }

  const original = globalThis.WebSocket;
  (globalThis as { WebSocket: unknown }).WebSocket = FakeDaemonWebSocket;
  try {
    const presence = connectDaemonPresence({
      baseUrl: 'http://example.com/',
      tokenPath,
    }) as unknown as { url: string; close: () => void };
    expect(presence.url).toBe('http://example.com/ws/daemon?token=token-789');
    presence.close();
  } finally {
    rmSync(dir, { recursive: true, force: true });
    (globalThis as { WebSocket: unknown }).WebSocket = original;
  }
});

test('connectTaskEvents includes daemon token query when token file exists', () => {
  const dir = mkdtempSync(join(tmpdir(), 'kl-events-token-'));
  const tokenPath = join(dir, 'daemon.token');
  writeFileSync(tokenPath, 'token-456');
  class FakeWebSocket {
    url: string;

    constructor(url: string) {
      this.url = url;
    }
  }

  const original = globalThis.WebSocket;
  (globalThis as { WebSocket: unknown }).WebSocket = FakeWebSocket;

  try {
    const socket = connectTaskEvents('t1', () => undefined, {
      baseUrl: 'http://example.com/',
      tokenPath,
    }) as unknown as FakeWebSocket;
    expect(socket.url).toBe('http://example.com/ws/tasks/t1?token=token-456');
  } finally {
    rmSync(dir, { recursive: true, force: true });
    (globalThis as { WebSocket: unknown }).WebSocket = original;
  }
});


test('connectTaskEventsWithReconnect reconnects after close with backoff', () => {
  class FakeReconnectingWebSocket {
    static instances: FakeReconnectingWebSocket[] = [];
    url: string;
    onmessage: ((event: { data: string }) => void) | null = null;
    onclose: (() => void) | null = null;
    close = () => undefined;

    constructor(url: string) {
      this.url = url;
      FakeReconnectingWebSocket.instances.push(this);
    }
  }

  const original = globalThis.WebSocket;
  (globalThis as { WebSocket: unknown }).WebSocket = FakeReconnectingWebSocket;
  vi.useFakeTimers();
  try {
    const socket = connectTaskEventsWithReconnect(
      't1',
      () => undefined,
      { baseUrl: 'http://example.com/' },
    );
    expect(FakeReconnectingWebSocket.instances).toHaveLength(1);
    FakeReconnectingWebSocket.instances[0].onclose?.();
    vi.advanceTimersByTime(1000);
    expect(FakeReconnectingWebSocket.instances).toHaveLength(2);
    socket.close();
  } finally {
    vi.useRealTimers();
    (globalThis as { WebSocket: unknown }).WebSocket = original;
  }
});

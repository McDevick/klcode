import { expect, test } from 'vitest';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { connectTaskEvents, type TaskEvent } from '../src/api/events';

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

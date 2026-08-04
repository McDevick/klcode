import { expect, test } from 'vitest';
import { connectTaskEvents, type TaskEvent } from '../src/api/events';

test('connectTaskEvents parses valid events and ignores malformed ones', () => {
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
  }) as unknown as FakeWebSocket;

  try {
    expect(socket.url).toBe('http://example.com/ws/tasks/t1');
    socket.onmessage?.({ data: JSON.stringify({ task_id: 't1', event: 'ok' }) });
    socket.onmessage?.({ data: 'bad json' });
    socket.onmessage?.({ data: JSON.stringify({ task_id: 't1' }) });
    expect(received).toEqual([{ task_id: 't1', event: 'ok' }]);
  } finally {
    (globalThis as { WebSocket: unknown }).WebSocket = original;
  }
});

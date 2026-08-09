import { DEFAULT_BASE_URL } from './client';
import { readDaemonToken } from './daemon-token';

export interface TaskEvent {
  task_id: string;
  event: string;
  event_id?: string;
  [key: string]: unknown;
}

export interface ConnectTaskEventsOptions {
  baseUrl?: string;
  tokenPath?: string;
}

export interface DaemonPresenceOptions {
  baseUrl?: string;
  tokenPath?: string;
}

export interface DaemonPresence {
  url: string;
  close: () => void;
}

export function connectDaemonPresence(
  options: DaemonPresenceOptions = {},
): DaemonPresence {
  const base = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, '');
  const token = readDaemonToken(options.tokenPath);
  const query = token ? `?token=${encodeURIComponent(token)}` : '';
  const url = `${base}/ws/daemon${query}`;

  class ReconnectingDaemonSocket implements DaemonPresence {
    readonly url: string;
    private socket: WebSocket;
    private closed = false;
    private attempt = 0;

    constructor(url: string) {
      this.url = url;
      this.socket = new WebSocket(url);
      this.socket.onopen = () => {
        this.attempt = 0;
      };
      this.socket.onclose = () => {
        if (this.closed) return;
        const delay = Math.min(1000 * 2 ** this.attempt, 30_000);
        this.attempt += 1;
        setTimeout(() => {
          if (this.closed) return;
          const next = new WebSocket(this.url);
          next.onopen = () => {
            this.attempt = 0;
          };
          next.onclose = this.socket.onclose;
          this.socket = next;
        }, delay);
      };
    }

    close(): void {
      this.closed = true;
      this.socket.close();
    }
  }

  return new ReconnectingDaemonSocket(url);
}

export interface ReconnectingTaskSocket {
  close: () => void;
}

export function connectTaskEventsWithReconnect(
  taskId: string,
  onEvent: (event: TaskEvent) => void,
  options: ConnectTaskEventsOptions = {},
): ReconnectingTaskSocket {
  const base = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, '');
  const token = readDaemonToken(options.tokenPath);
  const query = token ? `?token=${encodeURIComponent(token)}` : '';
  const url = `${base}/ws/tasks/${encodeURIComponent(taskId)}${query}`;
  const seenEventIds = new Set<string>();

  class ReconnectingTaskSocketImpl implements ReconnectingTaskSocket {
    private socket: WebSocket;
    private closed = false;
    private attempt = 0;

    constructor() {
      this.socket = new WebSocket(url);
      this.socket.onmessage = (message) => {
        try {
          const data = JSON.parse(String(message.data)) as unknown;
          if (
            data &&
            typeof data === 'object' &&
            'task_id' in data &&
            typeof (data as TaskEvent).event === 'string'
          ) {
            const event = data as TaskEvent;
            if (typeof event.event_id === 'string') {
              if (seenEventIds.has(event.event_id)) return;
              seenEventIds.add(event.event_id);
            }
            onEvent(event);
          }
        } catch {
          // Ignore malformed websocket messages.
        }
      };
      this.socket.onclose = () => {
        if (this.closed) return;
        const delay = Math.min(1000 * 2 ** this.attempt, 30_000);
        this.attempt += 1;
        setTimeout(() => {
          if (this.closed) return;
          const next = new WebSocket(url);
          next.onmessage = this.socket.onmessage;
          next.onclose = this.socket.onclose;
          this.socket = next;
        }, delay);
      };
    }

    close(): void {
      this.closed = true;
      this.socket.close();
    }
  }

  return new ReconnectingTaskSocketImpl();
}

export function connectTaskEvents(
  taskId: string,
  onEvent: (event: TaskEvent) => void,
  options: ConnectTaskEventsOptions = {},
): WebSocket {
  const base = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, '');
  const token = readDaemonToken(options.tokenPath);
  const query = token ? `?token=${encodeURIComponent(token)}` : '';
  const socket = new WebSocket(`${base}/ws/tasks/${encodeURIComponent(taskId)}${query}`);
  socket.onmessage = (message) => {
    try {
      const data = JSON.parse(String(message.data)) as unknown;
      if (
        data &&
        typeof data === 'object' &&
        'task_id' in data &&
        typeof (data as TaskEvent).event === 'string'
      ) {
        onEvent(data as TaskEvent);
      }
    } catch {
      // Ignore malformed websocket messages.
    }
  };
  return socket;
}
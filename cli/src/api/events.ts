import { DEFAULT_BASE_URL } from './client';

export interface TaskEvent {
  task_id: string;
  event: string;
  [key: string]: unknown;
}

export interface ConnectTaskEventsOptions {
  baseUrl?: string;
}

export function connectTaskEvents(
  taskId: string,
  onEvent: (event: TaskEvent) => void,
  options: ConnectTaskEventsOptions = {},
): WebSocket {
  const base = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, '');
  const socket = new WebSocket(`${base}/ws/tasks/${encodeURIComponent(taskId)}`);
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

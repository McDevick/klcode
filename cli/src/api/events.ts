export interface TaskEvent {
  task_id: string;
  event: string;
  [key: string]: unknown;
}

const DEFAULT_BASE_URL = 'http://127.0.0.1:8700';

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

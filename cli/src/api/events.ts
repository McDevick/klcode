export interface TaskEvent {
  task_id: string;
  event: string;
  [key: string]: unknown;
}

const DEFAULT_BASE_URL = 'http://127.0.0.1:8700';

export function connectTaskEvents(
  taskId: string,
  onEvent: (event: TaskEvent) => void,
): WebSocket {
  const socket = new WebSocket(`${DEFAULT_BASE_URL}/ws/tasks/${taskId}`);
  socket.onmessage = (message) => {
    onEvent(JSON.parse(String(message.data)) as TaskEvent);
  };
  return socket;
}

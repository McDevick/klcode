export interface TaskEvent {
  task_id: string;
  event: string;
  [key: string]: unknown;
}

export function connectTaskEvents(
  baseUrl: string,
  taskId: string,
  onEvent: (event: TaskEvent) => void,
): WebSocket {
  const socket = new WebSocket(`${baseUrl.replace(/\/$/, '')}/ws/tasks/${taskId}`);
  socket.onmessage = (message) => {
    onEvent(JSON.parse(String(message.data)) as TaskEvent);
  };
  return socket;
}

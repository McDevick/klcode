export interface ToolCall {
  name: string;
  args: string;
  summary: string;
}

export interface RunningTask {
  taskId: string;
  startedAt: number;
  steps: number;
  toolCalls: ToolCall[];
}

export type MessageKind = 'text' | 'info' | 'error' | 'done';

export interface ChatMessage {
  id: number;
  role: 'user' | 'agent';
  content: string;
  kind: MessageKind;
}

export interface ApprovalRequest {
  actionId: string;
  tool: string;
  command: string;
  level: string;
}

export interface SlashCommand {
  name: string;
  desc: string;
}

export interface RunningTask {
  taskId: string;
  startedAt: number;
  /** 已完成的工具调用次数 */
  steps: number;
}

export type MessageKind = 'text' | 'info' | 'error' | 'done' | 'tool';

export interface ChatMessage {
  id: number;
  role: 'user' | 'agent';
  content: string;
  kind: MessageKind;
  /** kind === 'tool' 时携带工具调用信息（名称/参数摘要/结果摘要） */
  tool?: {
    name: string;
    args: string;
    summary: string;
    ok: boolean;
  };
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

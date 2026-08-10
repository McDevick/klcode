import { homedir } from 'node:os';
import { join } from 'node:path';
import { readDaemonToken } from './daemon-token';

export interface ApiClientOptions {
  baseUrl: string;
  tokenPath?: string;
}

export const DEFAULT_BASE_URL = 'http://127.0.0.1:8700';

export interface ConfigCheckResult {
  status: string;
  providers?: string[];
}

export interface TaskResult {
  id: string;
  session_id: string;
  description: string;
  status: string;
}

export interface ModelConfig {
  provider: string;
  model: string;
  max_context: number;
  available: Array<{
    provider: string;
    model: string;
    base_url: string;
    max_context: number;
  }>;
}

export interface ContextSection {
  name: string;
  tokens: number;
  percent: number;
}

export interface ContextStatus {
  max_tokens: number;
  used_tokens: number;
  remaining_tokens: number;
  sections: ContextSection[];
}

export interface ProviderResult {
  name: string;
  type: string;
  base_url?: string;
  default_model?: string;
  credential_ref?: string | null;
}

export interface SkillInfo {
  name: string;
  description: string;
  keywords?: string[];
  when_to_use?: string;
  summary?: string;
  always_on?: boolean;
  sections?: string[];
}

export interface McpToolInfo {
  name: string;
  remote_name: string;
  description: string;
}

export interface McpServerInfo {
  name: string;
  command?: string;
  url?: string;
  args?: string[];
  tools?: McpToolInfo[];
  status?: string;
  error?: string;
}

export interface McpServerInput {
  name: string;
  command?: string;
  url?: string;
  args?: string[];
}

export interface ProviderInput {
  name: string;
  type: string;
  base_url: string;
  default_model: string;
}

export interface KeyStatusResult {
  configured: boolean;
}

export interface KeysResult {
  configured: string[];
}

export interface HealthResult {
  status: string;
}

export interface DaemonStatus {
  source: string;
  running_tasks: number;
  ws_connections: number;
}

export interface SessionHistoryMessage {
  type: 'user' | 'agent' | 'tool';
  content?: string;
  kind?: 'text' | 'error' | 'feedback' | 'warning';
  name?: string;
  args?: Record<string, unknown> | null;
  ok?: boolean;
  error?: string | null;
  output?: string | null;
}

function defaultTokenPath(): string {
  return join(homedir(), '.kl', 'daemon.token');
}

export class ApiClient {
  private readonly tokenPath: string;

  constructor(private readonly options: ApiClientOptions) {
    this.tokenPath = options.tokenPath ?? defaultTokenPath();
  }

  taskUrl(taskId: string): string {
    const base = this.options.baseUrl.replace(/\/+$/, '');
    return `${base}/api/v1/tasks/${encodeURIComponent(taskId)}`;
  }

  async request<T>(path: string, init?: RequestInit, timeoutMs = 5000): Promise<T> {
    const base = this.options.baseUrl.replace(/\/+$/, '');
    const headers = new Headers(init?.headers);
    const token = readDaemonToken(this.tokenPath);
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    const response = await fetch(`${base}${path}`, {
      ...init,
      headers,
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) {
      throw new Error(`request failed: ${response.status}`);
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }

  listSessions(): Promise<
    Array<{ id: string; workspace?: string; name?: string; status?: string; task_count?: number }>
  > {
    return this.request('/api/v1/sessions');
  }

  getSession(id: string): Promise<{ id: string }> {
    return this.request(`/api/v1/sessions/${encodeURIComponent(id)}`);
  }

  getSessionHistory(id: string): Promise<SessionHistoryMessage[]> {
    return this.request(`/api/v1/sessions/${encodeURIComponent(id)}/history`);
  }

  getContextStatus(id: string): Promise<ContextStatus> {
    return this.request(`/api/v1/sessions/${encodeURIComponent(id)}/context`);
  }

  compactContext(id: string): Promise<ContextStatus> {
    return this.request(`/api/v1/sessions/${encodeURIComponent(id)}/context/compact`, {
      method: 'POST',
    }, 120000);
  }

  createSession(payload: { workspace: string; name?: string }): Promise<{ id: string }> {
    return this.request('/api/v1/sessions', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }

  renameSession(id: string, name: string): Promise<{ id: string }> {
    return this.request(`/api/v1/sessions/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ name }),
    });
  }

  closeSession(id: string): Promise<{ id: string }> {
    return this.request(`/api/v1/sessions/${encodeURIComponent(id)}/close`, { method: 'POST' });
  }

  deleteSession(id: string): Promise<{ id: string }> {
    return this.request(`/api/v1/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' });
  }

  ensureConfigured(): Promise<ConfigCheckResult> {
    return this.request('/api/v1/config/check', { method: 'POST' });
  }

  daemonStatus(): Promise<DaemonStatus> {
    return this.request('/daemon/status');
  }

  runTask(taskId: string): Promise<{ status: string }> {
    return this.request(`/api/v1/tasks/${encodeURIComponent(taskId)}/run`, {
      method: 'POST',
    });
  }

  abortTask(taskId: string): Promise<{ status: string }> {
    return this.request(`/api/v1/tasks/${encodeURIComponent(taskId)}/abort`, {
      method: 'POST',
    });
  }

  addTaskInstruction(
    taskId: string,
    instruction: string,
  ): Promise<{ task_id: string; status: string }> {
    return this.request(`/api/v1/tasks/${encodeURIComponent(taskId)}/instructions`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ instruction }),
    });
  }

  pauseTask(taskId: string): Promise<{ status: string }> {
    return this.request(`/api/v1/tasks/${encodeURIComponent(taskId)}/pause`, {
      method: 'POST',
    });
  }

  continueTask(taskId: string): Promise<{ status: string }> {
    return this.request(`/api/v1/tasks/${encodeURIComponent(taskId)}/continue`, {
      method: 'POST',
    });
  }

  createTask(description: string, sessionId = 'default'): Promise<TaskResult> {
    return this.request('/api/v1/tasks', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, description }),
    });
  }

  listProviders(): Promise<ProviderResult[]> {
    return this.request('/api/v1/providers');
  }

  addProvider(payload: ProviderInput): Promise<ProviderResult> {
    return this.request('/api/v1/providers', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }

  testProvider(name: string): Promise<{ ok: boolean; provider: string; error?: string; model?: string }> {
    return this.request(`/api/v1/providers/${encodeURIComponent(name)}/test`, {
      method: 'POST',
    }, 120000);
  }

  listKeys(): Promise<KeysResult> {
    return this.request('/api/v1/keys');
  }

  setKey(ref: string, secret: string): Promise<KeyStatusResult> {
    return this.request(`/api/v1/keys/${encodeURIComponent(ref)}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ secret }),
    });
  }

  keyStatus(ref: string): Promise<KeyStatusResult> {
    return this.request(`/api/v1/keys/${encodeURIComponent(ref)}`);
  }

  clearKey(ref: string): Promise<KeyStatusResult> {
    return this.request(`/api/v1/keys/${encodeURIComponent(ref)}`, { method: 'DELETE' });
  }

  health(): Promise<HealthResult> {
    return this.request('/health');
  }

  getModelConfig(): Promise<ModelConfig> {
    return this.request('/api/v1/config/model');
  }

  setModelConfig(payload: { provider: string; model?: string }): Promise<ModelConfig> {
    return this.request('/api/v1/config/model', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ provider: payload.provider, model: payload.model ?? '' }),
    });
  }

  listModels(): Promise<Array<{ provider: string; model: string; base_url: string }>> {
    return this.request('/api/v1/models');
  }

  listSkills(): Promise<SkillInfo[]> {
    return this.request('/api/v1/skills');
  }

  listMcpServers(): Promise<McpServerInfo[]> {
    return this.request('/api/v1/mcp');
  }

  addMcpServer(payload: McpServerInput): Promise<McpServerInfo> {
    return this.request('/api/v1/mcp', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    }, 120000);
  }

  refreshMcpServer(name: string): Promise<McpServerInfo> {
    return this.request(`/api/v1/mcp/${encodeURIComponent(name)}/refresh`, {
      method: 'POST',
    }, 120000);
  }

  removeMcpServer(name: string): Promise<void> {
    return this.request(`/api/v1/mcp/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    });
  }
}

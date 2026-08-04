export interface ApiClientOptions {
  baseUrl: string;
}

export class ApiClient {
  constructor(private readonly options: ApiClientOptions) {}

  taskUrl(taskId: string): string {
    const base = this.options.baseUrl.replace(/\/+$/, '');
    return `${base}/api/v1/tasks/${encodeURIComponent(taskId)}`;
  }

  async request<T>(path: string, init?: RequestInit): Promise<T> {
    const base = this.options.baseUrl.replace(/\/+$/, '');
    const response = init ? await fetch(`${base}${path}`, init) : await fetch(`${base}${path}`);
    if (!response.ok) {
      throw new Error(`request failed: ${response.status}`);
    }
    return (await response.json()) as T;
  }

  listSessions(): Promise<Array<{ id: string }>> {
    return this.request('/api/v1/sessions');
  }

  getSession(id: string): Promise<{ id: string }> {
    return this.request(`/api/v1/sessions/${encodeURIComponent(id)}`);
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
}

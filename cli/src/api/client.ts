export interface ApiClientOptions {
  baseUrl: string;
}

export class ApiClient {
  constructor(private readonly options: ApiClientOptions) {}

  taskUrl(taskId: string): string {
    const base = this.options.baseUrl.replace(/\/+$/, '');
    return `${base}/api/v1/tasks/${encodeURIComponent(taskId)}`;
  }

  async request<T>(path: string): Promise<T> {
    const base = this.options.baseUrl.replace(/\/+$/, '');
    const response = await fetch(`${base}${path}`);
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
}

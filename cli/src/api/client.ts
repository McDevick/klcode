export interface ApiClientOptions {
  baseUrl: string;
}

export class ApiClient {
  constructor(private readonly options: ApiClientOptions) {}

  taskUrl(taskId: string): string {
    return `${this.options.baseUrl}/api/v1/tasks/${taskId}`;
  }
}

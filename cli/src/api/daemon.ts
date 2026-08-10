import { ApiClient, DEFAULT_BASE_URL } from './client';
import { ServerCommand } from '../commands/server';

export interface AutoStartDaemonOptions {
  client?: ApiClient;
  serverStart?: (args: string[]) => Promise<string>;
  healthCheck?: (client: ApiClient) => Promise<boolean>;
  waitTimeoutMs?: number;
}

export function isConnectionError(error: unknown): boolean {
  const message = String(error instanceof Error ? error.message : error);
  return (
    message.includes('ECONNREFUSED') ||
    message.includes('fetch failed') ||
    message.includes('NetworkError') ||
    message.includes('network')
  );
}

export async function waitForHealth(
  client: ApiClient,
  timeoutMs: number,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      await client.health();
      return true;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  return false;
}

export async function autoStartDaemon(
  options: AutoStartDaemonOptions = {},
): Promise<boolean> {
  const client = options.client ?? new ApiClient({ baseUrl: DEFAULT_BASE_URL });
  const serverStart =
    options.serverStart ??
    ((serverArgs: string[]) => ServerCommand.run(serverArgs, { source: 'auto' }));
  const healthCheck =
    options.healthCheck ??
    ((candidate: ApiClient) =>
      waitForHealth(candidate, options.waitTimeoutMs ?? 10_000));

  const startResult = await serverStart(['start']);
  if (startResult.startsWith('server start failed')) {
    return false;
  }
  return healthCheck(client);
}

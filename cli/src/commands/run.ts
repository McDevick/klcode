import { ApiClient, DEFAULT_BASE_URL } from '../api/client';
import { autoStartDaemon, isConnectionError } from '../api/daemon';

export interface RunCommandOptions {
  client?: ApiClient;
  serverStart?: (args: string[]) => Promise<string>;
  healthCheck?: (client: ApiClient) => Promise<boolean>;
  waitTimeoutMs?: number;
}

async function createOneOffTask(
  client: ApiClient,
  description: string,
): Promise<string> {
  const session = await client.createSession({ workspace: process.cwd() });
  const task = await client.createTask(description, session.id);
  return `task ${task.id} created (${task.status})`;
}

export const RunCommand = {
  name: 'run',
  run: async (args: string[], options: RunCommandOptions = {}): Promise<string> => {
    const description = args.join(' ').trim();
    if (!description) {
      return 'usage: kl run "<task>"';
    }

    const client = options.client ?? new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    try {
      return await createOneOffTask(client, description);
    } catch (error) {
      if (!isConnectionError(error)) {
        throw error;
      }
      const started = await autoStartDaemon({
        client,
        serverStart: options.serverStart,
        healthCheck: options.healthCheck,
        waitTimeoutMs: options.waitTimeoutMs,
      });
      if (!started) {
        return 'run failed: daemon not running and auto-start failed';
      }
      return await createOneOffTask(client, description);
    }
  },
};

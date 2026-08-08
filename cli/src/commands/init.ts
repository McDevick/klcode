import { ApiClient, DEFAULT_BASE_URL } from '../api/client';
import { ServerCommand } from './server';

interface InitCommandOptions {
  /** 测试注入点：替换服务端拉起逻辑 */
  serverStart?: (args: string[]) => Promise<string>;
  /** 测试注入点：替换就绪探测 */
  healthCheck?: (client: ApiClient) => Promise<boolean>;
  waitTimeoutMs?: number;
  client?: ApiClient;
}

function isConnectionError(error: unknown): boolean {
  const message = String(error instanceof Error ? error.message : error);
  return (
    message.includes('ECONNREFUSED') ||
    message.includes('fetch failed') ||
    message.includes('NetworkError') ||
    message.includes('network')
  );
}

async function waitForHealth(
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

function formatStatus(result: { status: string; providers?: string[] }): string {
  const providers = result.providers?.join(', ') || 'none';
  const missing = result.providers?.length ? 'none' : 'provider configuration';
  return [
    `initialization status: ${result.status}`,
    `providers: ${providers}`,
    `missing: ${missing}`,
    'next: kl config provider list and kl config key show <ref>',
  ].join('\n');
}

export const InitCommand = {
  name: 'init',
  run: async (args: string[], options: InitCommandOptions = {}): Promise<string> => {
    const client = options.client ?? new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    const serverStart =
      options.serverStart ?? ((serverArgs: string[]) => ServerCommand.run(serverArgs));
    const healthCheck =
      options.healthCheck ??
      ((candidate: ApiClient) => waitForHealth(candidate, options.waitTimeoutMs ?? 10_000));

    try {
      return formatStatus(await client.ensureConfigured());
    } catch (error) {
      // 冷启动场景：仅当连接被拒（服务端未运行）时自动拉起 daemon 后重试；
      // HTTP 类错误（服务在跑但配置/服务端有问题）不启动，直接原样报错。
      if (!isConnectionError(error)) {
        throw error;
      }
      const startResult = await serverStart(['start']);
      if (startResult.startsWith('server start failed')) {
        return `init failed: daemon not running and auto-start failed\n${startResult}`;
      }
      const ready = await healthCheck(client);
      if (!ready) {
        return `init failed: daemon not responding after auto-start\n${startResult}`;
      }
      return formatStatus(await client.ensureConfigured());
    }
  },
};

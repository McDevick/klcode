import { ApiClient, DEFAULT_BASE_URL } from '../api/client';

export const InitCommand = {
  name: 'init',
  run: async (): Promise<string> => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    const result = await client.ensureConfigured();
    const providers = result.providers?.join(', ') || 'none';
    const missing = result.providers?.length ? 'none' : 'provider configuration';

    return [
      `initialization status: ${result.status}`,
      `providers: ${providers}`,
      `missing: ${missing}`,
      'next: kl config provider list and kl config key show <ref>',
    ].join('\n');
  },
};

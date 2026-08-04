import { ApiClient, DEFAULT_BASE_URL } from '../api/client';

export const ConfigCommand = {
  name: 'config',
  aliases: ['/cfg'],
  run: (args: string[]): string | Promise<string> => {
    const [area, subcommand, ...rest] = args;
    if (area === 'provider') {
      return runProvider(subcommand, rest);
    }
    if (area === 'key') {
      return runKey(subcommand, rest);
    }
    return 'opening config wizard';
  },
};

async function runProvider(subcommand: string | undefined, rest: string[]): Promise<string> {
  const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });

  switch (subcommand) {
    case 'add': {
      const [name, type, baseUrl, defaultModel] = rest;
      if (!name || !type || !baseUrl || !defaultModel) {
        return 'usage: kl config provider add <name> <type> <base-url> <default-model>';
      }
      return JSON.stringify(
        await client.addProvider({
          name,
          type,
          base_url: baseUrl,
          default_model: defaultModel,
        }),
      );
    }
    case 'list':
      return JSON.stringify(await client.listProviders());
    case 'test': {
      const providers = await client.listProviders();
      const name = rest[0];
      const available = name
        ? providers.some((provider) => provider.name === name)
        : providers.length > 0;
      return available
        ? `provider test ok${name ? ` (${name})` : ''}`
        : `provider test failed${name ? ` (${name})` : ''}`;
    }
    default:
      return 'usage: kl config provider add|list|test';
  }
}

async function runKey(subcommand: string | undefined, rest: string[]): Promise<string> {
  const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });

  switch (subcommand) {
    case 'set': {
      const [ref, secret] = rest;
      if (!ref || !secret) {
        return 'usage: kl config key set <ref> <secret>';
      }
      const status = await client.setKey(ref, secret);
      return `configured: ${status.configured}`;
    }
    case 'test':
    case 'show': {
      const [ref] = rest;
      if (!ref) {
        const keys = await client.listKeys();
        return `configured: ${keys.configured.join(', ') || 'none'}`;
      }
      const status = await client.keyStatus(ref);
      return `configured: ${status.configured}`;
    }
    case 'clear': {
      const [ref] = rest;
      if (!ref) {
        return 'usage: kl config key clear <ref>';
      }
      const status = await client.clearKey(ref);
      return `configured: ${status.configured}`;
    }
    default:
      return 'usage: kl config key set|test|clear|show';
  }
}

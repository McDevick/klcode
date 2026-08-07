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
    if (area === 'model') {
      return runModel(subcommand, rest);
    }
    if (area === 'mcp') {
      return runMcp(subcommand, rest);
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

async function runModel(subcommand: string | undefined, rest: string[]): Promise<string> {
  const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });

  switch (subcommand) {
    case 'set': {
      const [provider, model] = rest;
      if (!provider) {
        return 'usage: kl config model set <provider> [model]';
      }
      const state = await client.setModelConfig(model ? { provider, model } : { provider });
      return `model: ${state.provider} / ${state.model}`;
    }
    case 'show': {
      const state = await client.getModelConfig();
      return `provider: ${state.provider}\nmodel: ${state.model}`;
    }
    case 'list': {
      const available = await client.listModels();
      return available.map((item) => `${item.provider}: ${item.model}`).join('\n');
    }
    default:
      return 'usage: kl config model set|show|list';
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

async function runMcp(subcommand: string | undefined, rest: string[]): Promise<string> {
  const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });

  switch (subcommand) {
    case 'list': {
      const servers = await client.listMcpServers();
      if (servers.length === 0) {
        return 'no mcp servers configured';
      }
      return servers
        .map((server) => {
          const transport = server.url
            ? `url ${server.url}`
            : `command ${server.command ?? ''} ${(server.args ?? []).join(' ')}`.trim();
          return `${server.name}: ${transport} (${server.tools?.length ?? 0} tools)`;
        })
        .join('\n');
    }
    case 'add': {
      const [name, kind, value, ...args] = rest;
      if (!name || !kind || !value) {
        return 'usage: kl config mcp add <name> url <url> | kl config mcp add <name> command <command> [args...]';
      }
      const payload =
        kind === 'url'
          ? { name, url: value }
          : kind === 'command'
            ? { name, command: value, args }
            : null;
      if (payload === null) {
        return 'usage: kl config mcp add <name> url <url> | kl config mcp add <name> command <command> [args...]';
      }
      const server = await client.addMcpServer(payload);
      return `mcp server added: ${server.name} (${server.tools?.length ?? 0} tools)`;
    }
    case 'refresh': {
      const [name] = rest;
      if (!name) {
        return 'usage: kl config mcp refresh <name>';
      }
      const server = await client.refreshMcpServer(name);
      return `mcp server refreshed: ${server.name} (${server.tools?.length ?? 0} tools)`;
    }
    case 'remove': {
      const [name] = rest;
      if (!name) {
        return 'usage: kl config mcp remove <name>';
      }
      await client.removeMcpServer(name);
      return `mcp server removed: ${name}`;
    }
    case 'tools': {
      const [name] = rest;
      const servers = await client.listMcpServers();
      const selected = name
        ? servers.filter((server) => server.name === name)
        : servers;
      const lines = selected.flatMap((server) =>
        (server.tools ?? []).map((tool) => `${server.name}: ${tool.name} (${tool.remote_name})`),
      );
      return lines.length > 0 ? lines.join('\n') : 'no mcp tools';
    }
    default:
      return 'usage: kl config mcp list|tools|add|refresh|remove';
  }
}

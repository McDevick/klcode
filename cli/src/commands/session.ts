import { ApiClient, DEFAULT_BASE_URL } from '../api/client';

export const SessionCommand = {
  name: 'session',
  aliases: ['/sessions'],
  run: async (args: string[]) => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    const [subcommand, value, ...rest] = args;
    switch (subcommand) {
      case 'new':
        if (!value) return 'usage: /session new <workspace>';
        return JSON.stringify(await client.createSession({ workspace: value }));
      case 'open':
        if (!value) return 'usage: /session open <id>';
        return JSON.stringify(await client.getSession(value));
      case 'rename':
        if (!value || rest.length === 0) return 'usage: /session rename <id> <name>';
        return JSON.stringify(await client.renameSession(value, rest.join(' ')));
      case 'close':
        if (!value) return 'current session close is not wired yet';
        return JSON.stringify(await client.closeSession(value));
      case 'delete':
        if (!value) return 'usage: /session delete <id>';
        return JSON.stringify(await client.deleteSession(value));
      default:
        return JSON.stringify(await client.listSessions());
    }
  },
};

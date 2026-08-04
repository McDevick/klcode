import { ApiClient } from '../api/client';

export const SessionCommand = {
  name: 'session',
  aliases: ['/sessions'],
  run: async (args: string[]) => {
    const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700' });
    const [subcommand, value, second] = args;
    switch (subcommand) {
      case 'new':
        if (!value) return 'usage: /session new <workspace>';
        return JSON.stringify(await client.createSession({ workspace: value }));
      case 'open':
        if (!value) return 'usage: /session open <id>';
        return JSON.stringify(await client.getSession(value));
      case 'rename':
        if (!value || !second) return 'usage: /session rename <id> <name>';
        return JSON.stringify(await client.renameSession(value, second));
      case 'close':
        if (!value) return 'usage: /session close <id>';
        return JSON.stringify(await client.closeSession(value));
      case 'delete':
        if (!value) return 'usage: /session delete <id>';
        return JSON.stringify(await client.deleteSession(value));
      default:
        return JSON.stringify(await client.listSessions());
    }
  },
};

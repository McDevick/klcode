import { ApiClient } from '../api/client';

export const SessionCommand = {
  name: 'session',
  aliases: ['/sessions'],
  run: async (args: string[]) => {
    const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700' });
    if (args[0] === 'open' && args[1]) {
      return JSON.stringify(await client.getSession(args[1]));
    }
    return JSON.stringify(await client.listSessions());
  },
};

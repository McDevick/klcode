import { ApiClient, DEFAULT_BASE_URL } from '../api/client';

export const RunCommand = {
  name: 'run',
  run: async (args: string[]): Promise<string> => {
    const description = args.join(' ').trim();
    if (!description) {
      return 'usage: kl run "<task>"';
    }

    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    const session = await client.createSession({ workspace: process.cwd() });
    const task = await client.createTask(description, session.id);
    return `task ${task.id} created (${task.status})`;
  },
};

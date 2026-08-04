import { ApiClient, DEFAULT_BASE_URL } from '../api/client';

export const RunCommand = {
  name: 'run',
  run: async (args: string[]): Promise<string> => {
    const description = args.join(' ').trim();
    if (!description) {
      return 'usage: kl run "<task>"';
    }

    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    const task = await client.createTask(description);
    return `task ${task.id} created (${task.status})`;
  },
};

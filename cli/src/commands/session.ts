import { ApiClient, DEFAULT_BASE_URL } from '../api/client';

interface SessionRecord {
  id: string;
  workspace?: string;
  name?: string;
  status?: string;
}

function formatSession(session: SessionRecord): string {
  const parts = [`${session.id}`];
  if (session.name) parts.push(`名称: ${session.name}`);
  if (session.status) parts.push(`状态: ${session.status}`);
  if (session.workspace) parts.push(`目录: ${session.workspace}`);
  return parts.join('  ');
}

export const SessionCommand = {
  name: 'session',
  aliases: ['/sessions'],
  run: async (args: string[]) => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    const [subcommand, value, ...rest] = args;
    switch (subcommand) {
      case 'new':
        if (!value) return 'usage: /session new <workspace>';
        const created = await client.createSession({ workspace: value });
        return `会话已创建: ${formatSession(created)}`;
      case 'open':
        if (!value) return 'usage: /session open <id>';
        const opened = await client.getSession(value);
        return `会话 ${formatSession(opened)}`;
      case 'rename':
        if (!value || rest.length === 0) return 'usage: /session rename <id> <name>';
        await client.renameSession(value, rest.join(' '));
        return `会话 ${value} 已重命名: ${rest.join(' ')}`;
      case 'close':
        if (!value) return 'current session close is not wired yet';
        await client.closeSession(value);
        return `会话 ${value} 已关闭`;
      case 'delete':
        if (!value) return 'usage: /session delete <id>';
        await client.deleteSession(value);
        return `会话 ${value} 已删除`;
      default: {
        const sessions = await client.listSessions();
        if (sessions.length === 0) {
          return '暂无历史会话';
        }
        return `历史会话 (${sessions.length}):\n${sessions
          .map((session) => `  ${formatSession(session)}`)
          .join('\n')}`;
      }
    }
  },
};

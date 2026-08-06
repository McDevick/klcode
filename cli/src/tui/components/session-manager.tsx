import React, { useEffect, useState } from 'react';
import { Box, Text, useInput, useStdin, useStdout } from 'ink';
import { ApiClient, DEFAULT_BASE_URL } from '../../api/client';
import { theme } from '../theme';

interface SessionRecord {
  id: string;
  workspace?: string;
  name?: string;
  status?: string;
  task_count?: number;
}

type SessionItem =
  | { kind: 'session'; session: SessionRecord }
  | { kind: 'new' };

const ACTIONS = [
  { key: 'enter', label: 'Enter' },
  { key: 'delete', label: 'Delete' },
  { key: 'rename', label: 'Rename' },
] as const;

function displayName(session: SessionRecord): string {
  const name = session.name?.trim();
  if (!name || name === 'default') return session.id;
  return `${session.id} · ${name}`;
}

export function SessionManager({
  currentSessionId,
  workspace,
  mouseTracking,
  onEnter,
  onClose,
}: {
  currentSessionId: string | null;
  workspace: string;
  mouseTracking: boolean;
  onEnter: (id: string) => void;
  onClose: () => void;
}) {
  const { stdout } = useStdout();
  const { stdin } = useStdin();
  const maxVisible = Math.max(2, Math.min(5, Math.floor((stdout.rows ?? 24) / 4)));
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [actionIndex, setActionIndex] = useState(0);
  const [mode, setMode] = useState<'browse' | 'rename'>('browse');
  const [renameValue, setRenameValue] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const items: SessionItem[] = [
    ...sessions.map((session) => ({ kind: 'session' as const, session })),
    { kind: 'new' },
  ];

  const loadSessions = async () => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    try {
      const records = await client.listSessions();
      setSessions(records);
      setSelectedIndex((index) => Math.min(index, Math.max(0, records.length)));
      setActionIndex(0);
      setError('');
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadSessions();
  }, []);

  useEffect(() => {
    process.stdout.write('\x1b[?1000h\x1b[?1006h');
    return () => {
      if (!mouseTracking) {
        process.stdout.write('\x1b[?1000l\x1b[?1006l');
      }
    };
  }, [mouseTracking]);

  const selectedSession =
    selectedIndex >= sessions.length ? null : sessions[selectedIndex];

  const createSession = async () => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    setBusy(true);
    setError('');
    try {
      const created = await client.createSession({ workspace });
      await loadSessions();
      onEnter(created.id);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const deleteSession = async (target: SessionRecord) => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    setBusy(true);
    setError('');
    try {
      await client.deleteSession(target.id);
      if (target.id === currentSessionId) {
        const created = await client.createSession({ workspace });
        await loadSessions();
        onEnter(created.id);
        return;
      }
      await loadSessions();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const startRenameSession = (target: SessionRecord) => {
    setRenameValue(displayName(target));
    setMode('rename');
    setError('');
  };

  const submitRename = async (target: SessionRecord) => {
    const name = renameValue.trim();
    if (!name) {
      setError('会话名称不能为空');
      return;
    }
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    setBusy(true);
    setError('');
    try {
      await client.renameSession(target.id, name);
      setMode('browse');
      await loadSessions();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const runSelectedAction = () => {
    if (selectedIndex >= sessions.length) {
      void createSession();
      return;
    }
    if (!selectedSession) return;
    const action = ACTIONS[actionIndex].key;
    if (action === 'enter') {
      onEnter(selectedSession.id);
    } else if (action === 'delete') {
      void deleteSession(selectedSession);
    } else {
      startRenameSession(selectedSession);
    }
  };

  const historyIndex = Math.min(selectedIndex, Math.max(0, sessions.length - 1));
  const windowStart = Math.max(
    0,
    Math.min(historyIndex - maxVisible + 1, sessions.length - maxVisible),
  );
  const visibleSessions = sessions.slice(windowStart, windowStart + maxVisible);
  const visibleItems: SessionItem[] = [
    ...visibleSessions.map((session) => ({ kind: 'session' as const, session })),
    { kind: 'new' },
  ];

  useEffect(() => {
    const onData = (chunk: Buffer) => {
      const match = /^\x1b\[<(\d+);(\d+);(\d+)([Mm])$/.exec(chunk.toString('utf8'));
      if (!match) return;
      const button = Number(match[1]);
      if (button !== 0) return;
      const x = Number(match[2]);
      const y = Number(match[3]);
      const rows = stdout.rows ?? 24;
      const columns = stdout.columns ?? 80;
      const fromBottom = rows - y;

      if (fromBottom === 0 && x >= columns - 10) {
        void createSession();
        return;
      }

      const extraRows = (busy ? 1 : 0) + (error ? 1 : 0) + (mode === 'rename' ? 1 : 0);
      const cardStart = extraRows + 1;
      const offset = fromBottom - cardStart - 1;
      if (offset < 0 || offset % 3 !== 0) return;
      const cardIndexFromBottom = offset / 3;
      const visibleIndex = visibleItems.length - 1 - cardIndexFromBottom;
      const item = visibleItems[visibleIndex];
      if (!item) return;
      if (item.kind === 'new') {
        setSelectedIndex(sessions.length);
        void createSession();
        return;
      }

      setSelectedIndex(windowStart + visibleIndex);
      if (x < columns - 30) return;
      if (x < columns - 20) {
        setActionIndex(0);
        onEnter(item.session.id);
      } else if (x < columns - 10) {
        setActionIndex(1);
        void deleteSession(item.session);
      } else {
        setActionIndex(2);
        startRenameSession(item.session);
      }
    };
    stdin.on('data', onData);
    return () => {
      stdin.off('data', onData);
    };
  }, [
    busy,
    createSession,
    deleteSession,
    error,
    mode,
    onEnter,
    sessions,
    startRenameSession,
    stdin,
    stdout.columns,
    stdout.rows,
    visibleItems,
    windowStart,
  ]);

  useInput((input, key) => {
    if (mode === 'rename') {
      if (key.escape) {
        setMode('browse');
        return;
      }
      if (key.return) {
        if (selectedSession) void submitRename(selectedSession);
        return;
      }
      if (key.backspace || key.delete) {
        setRenameValue((value) => value.slice(0, -1));
        return;
      }
      setRenameValue((value) => value + input);
      return;
    }
    if (key.escape) {
      onClose();
      return;
    }
    if (key.upArrow) {
      setSelectedIndex((index) => Math.max(0, index - 1));
      setActionIndex(0);
      return;
    }
    if (key.downArrow) {
      setSelectedIndex((index) => Math.min(items.length - 1, index + 1));
      setActionIndex(0);
      return;
    }
    if (key.leftArrow) {
      setActionIndex((index) => Math.max(0, index - 1));
      return;
    }
    if (key.rightArrow) {
      setActionIndex((index) => Math.min(ACTIONS.length - 1, index + 1));
      return;
    }
    if (key.return) {
      runSelectedAction();
      return;
    }
    if (input === '+') {
      void createSession();
      return;
    }
    if (input.toLowerCase() === 'd') {
      if (selectedSession) void deleteSession(selectedSession);
      return;
    }
    if (input.toLowerCase() === 'r') {
      if (selectedSession) startRenameSession(selectedSession);
    }
  });

  return (
    <Box
      flexDirection="column"
      width="100%"
      backgroundColor={theme.surface}
      paddingX={1}
      paddingTop={1}
    >
      <Box flexDirection="row">
        <Text bold color={theme.teal}>会话管理</Text>
        <Box flexGrow={1} />
      </Box>
      {loading ? <Text dimColor>加载中...</Text> : null}
      {!loading && visibleSessions.length === 0 ? <Text dimColor>暂无历史会话</Text> : null}
      {visibleItems.map((item, index) => {
        const absoluteIndex =
          item.kind === 'new' ? sessions.length : windowStart + index;
        const selected = absoluteIndex === selectedIndex;
        return (
          <Box
            key={item.kind === 'new' ? '__new__' : item.session.id}
            flexDirection="row"
            borderStyle="single"
            borderColor={selected ? theme.teal : theme.surfaceAlt}
            marginTop={1}
            paddingX={1}
          >
            {item.kind === 'new' ? (
              <>
                <Text bold color={selected ? theme.teal : theme.text}>
                  {selected ? '▸ ' : '  '}+ create new session
                </Text>
                <Box flexGrow={1} />
                <Text bold color={selected ? theme.teal : theme.textDim}>
                  {selected ? '[Enter]' : 'Enter'}
                </Text>
              </>
            ) : (
              <>
                <Text bold color={selected ? theme.teal : theme.text}>
                  {selected ? '▸ ' : '  '}
                  {displayName(item.session)}
                  {item.session.id === currentSessionId ? ' *' : ''}
                </Text>
                <Box flexGrow={1} />
                {ACTIONS.map((action, actionIdx) => (
                  <Text
                    key={action.key}
                    bold
                    color={selected && actionIdx === actionIndex ? theme.teal : theme.textDim}
                  >
                    {actionIdx > 0 ? '  ' : ''}
                    {selected && actionIdx === actionIndex ? `[${action.label}]` : action.label}
                  </Text>
                ))}
              </>
            )}
          </Box>
        );
      })}
      {mode === 'rename' ? (
        <Box marginTop={1}>
          <Text bold color={theme.yellow}>重命名: </Text>
          <Text>{renameValue}▍</Text>
        </Box>
      ) : null}
      {busy ? <Text dimColor>处理中...</Text> : null}
      {error ? <Text color={theme.red}>✗ {error}</Text> : null}
      <Box flexDirection="row" marginTop={1}>
        <Text dimColor>
          [↑/↓] 卡片 [←/→] 操作 [enter] 执行 [+] 新建 [d] 删除 [r] 重命名 [esc] 关闭
        </Text>
      </Box>
    </Box>
  );
}

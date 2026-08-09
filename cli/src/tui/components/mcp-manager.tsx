import React, { useEffect, useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { ApiClient, DEFAULT_BASE_URL, type McpServerInfo } from '../../api/client';
import { CommandMenu } from './command-menu';
import { theme } from '../theme';

export function McpManager({
  onClose,
}: {
  onClose: () => void;
}) {
  const [servers, setServers] = useState<McpServerInfo[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const load = async () => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    setLoading(true);
    setNotice('');
    try {
      const records = await client.listMcpServers();
      setServers(records);
      setSelectedIndex((index) => Math.max(0, Math.min(index, records.length - 1)));
    } catch (error: unknown) {
      setServers([]);
      setNotice(`读取失败: ${String(error)}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useInput((_input, key) => {
    if (key.escape) {
      setConfirmDelete(null);
      onClose();
      return;
    }
    if (key.upArrow) {
      setSelectedIndex((index) => Math.max(0, index - 1));
      setConfirmDelete(null);
      return;
    }
    if (key.downArrow) {
      setSelectedIndex((index) => Math.min(servers.length - 1, index + 1));
      setConfirmDelete(null);
      return;
    }
    const selected = servers[selectedIndex];
    if (!selected || busy) return;
    if (_input === 'r') {
      setBusy(true);
      setNotice('');
      const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
      client
        .refreshMcpServer(selected.name)
        .then((updated) => {
          setServers((current) =>
            current.map((server) => (server.name === updated.name ? updated : server)),
          );
          setNotice(
            updated.status === 'error'
              ? `刷新失败: ${updated.error ?? 'unknown error'}`
              : `已刷新: ${updated.name} (${updated.tools?.length ?? 0} tools)`,
          );
        })
        .catch((error: unknown) => {
          setNotice(`刷新失败: ${String(error)}`);
        })
        .finally(() => setBusy(false));
      return;
    }
    if (_input === 'd') {
      if (confirmDelete !== selected.name) {
        setConfirmDelete(selected.name);
        setNotice('再按 d 确认删除');
        return;
      }
      setBusy(true);
      setNotice('');
      const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
      client
        .removeMcpServer(selected.name)
        .then(() => {
          setServers((current) => current.filter((server) => server.name !== selected.name));
          setSelectedIndex((index) => Math.max(0, index - 1));
          setConfirmDelete(null);
          setNotice(`已删除: ${selected.name}`);
        })
        .catch((error: unknown) => {
          setNotice(`删除失败: ${String(error)}`);
        })
        .finally(() => setBusy(false));
    }
  });

  return (
    <Box flexDirection="column" width="100%" backgroundColor={theme.surface} paddingX={1}>
      <Text bold color={theme.teal}>
        MCP 管理
      </Text>
      {loading ? (
        <Text dimColor>正在加载 mcp servers…</Text>
      ) : servers.length === 0 ? (
        <Text dimColor>暂无已配置的 mcp server</Text>
      ) : (
        <CommandMenu
          commands={servers.map((server) => ({
            name: server.name,
            desc: server.status === 'error' ? (server.error ?? 'error') : '',
          }))}
          menuIndex={selectedIndex}
        />
      )}
      {notice ? (
        <Text color={notice.startsWith('已') ? theme.green : theme.red}>{notice}</Text>
      ) : null}
      <Text dimColor>[↑/↓] 选择 [r] 刷新 [d] 删除 [esc] 关闭</Text>
    </Box>
  );
}

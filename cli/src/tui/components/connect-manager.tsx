import React, { useEffect, useState } from 'react';
import { Box, Text, useInput, usePaste } from 'ink';
import { ApiClient, DEFAULT_BASE_URL, type ProviderResult } from '../../api/client';
import { theme } from '../theme';

export function ConnectManager({
  onClose,
}: {
  onClose: () => void;
}) {
  const [providers, setProviders] = useState<ProviderResult[]>([]);
  const [configuredKeys, setConfiguredKeys] = useState<string[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [view, setView] = useState<'list' | 'input'>('list');
  const [secret, setSecret] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  usePaste(
    (text) => {
      if (view !== 'input') return;
      setSecret((current) => current + text.replace(/[\r\n]+/g, ''));
    },
    { isActive: view === 'input' },
  );

  const load = async () => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    setLoading(true);
    setNotice('');
    try {
      const [providerRecords, keys] = await Promise.all([
        client.listProviders(),
        client.listKeys(),
      ]);
      setProviders(providerRecords.filter((provider) => provider.name !== 'mock'));
      setConfiguredKeys(keys.configured);
      setSelectedIndex((index) => Math.max(0, index - 1));
    } catch (error: unknown) {
      setNotice(`读取失败: ${String(error)}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const selectedProvider = providers[selectedIndex];

  const submitKey = async () => {
    if (!selectedProvider) return;
    if (!secret.trim()) {
      setNotice('API Key 不能为空');
      return;
    }
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    setBusy(true);
    setNotice('');
    try {
      await client.setKey(selectedProvider.name, secret);
      const [providerRecords, keys] = await Promise.all([
        client.listProviders(),
        client.listKeys(),
      ]);
      setProviders(providerRecords.filter((provider) => provider.name !== 'mock'));
      setConfiguredKeys(keys.configured);
      setNotice(`已保存: ${selectedProvider.name}`);
      setSecret('');
      setView('list');
    } catch (error: unknown) {
      setNotice(`保存失败: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  useInput((input, key) => {
    if (busy) return;
    if (view === 'list') {
      if (key.upArrow) {
        setSelectedIndex((index) => Math.max(0, index - 1));
        return;
      }
      if (key.downArrow) {
        setSelectedIndex((index) => Math.min(providers.length - 1, index + 1));
        return;
      }
      if (key.return && selectedProvider) {
        setSecret('');
        setNotice('');
        setView('input');
        return;
      }
      if (key.escape) {
        onClose();
      }
      return;
    }
    if (key.escape) {
      setSecret('');
      setNotice('');
      setView('list');
      return;
    }
    if (key.return) {
      void submitKey();
      return;
    }
    if (key.backspace || key.delete) {
      setSecret((current) => current.slice(0, -1));
      return;
    }
    if (input.length > 0) {
      setSecret((current) => current + input);
    }
  });

  return (
    <Box flexDirection="column" width="100%" backgroundColor={theme.surface} paddingX={1}>
      <Text bold color={theme.teal}>
        API 连接
      </Text>
      {view === 'list' ? (
        loading ? (
          <Text dimColor>正在加载 providers…</Text>
        ) : providers.length === 0 ? (
          <Text dimColor>暂无已配置 provider，请在配置文件中添加</Text>
        ) : (
          <Box flexDirection="column">
            {providers.map((provider, index) => {
              const secureRef = provider.credential_ref ?? '';
              const configured =
                secureRef !== '' && configuredKeys.includes(secureRef);
              const selected = index === selectedIndex;
              return (
                <Box
                  key={provider.name}
                  borderStyle="single"
                  borderColor={selected ? theme.teal : theme.border}
                  paddingX={1}
                  marginBottom={1}
                >
                  <Text color={selected ? theme.teal : theme.text}>
                    {selected ? '▸ ' : '  '}
                    {provider.name}
                  </Text>
                  <Text color={configured ? theme.green : theme.textDim}>
                    {configured ? '  ✓ 已配置' : '  未配置'}
                  </Text>
                </Box>
              );
            })}
          </Box>
        )
      ) : (
        <Box flexDirection="column">
          <Box
            borderStyle="single"
            borderColor={theme.blue}
            paddingX={1}
            flexDirection="column"
          >
            <Text color={theme.blue}>API Key for {selectedProvider?.name}:</Text>
            <Text color={theme.text}>
              {'•'.repeat(secret.length) || ' '}
              ▍
            </Text>
          </Box>
        </Box>
      )}
      {notice ? (
        <Text color={notice.startsWith('已保存') ? theme.green : theme.red}>{notice}</Text>
      ) : null}
      <Text dimColor>
        {view === 'list'
          ? '[↑/↓] 选择 [enter] 配置 API [esc] 关闭'
          : '[输入] API Key [enter] 保存 [backspace] 删除 [esc] 返回'}
      </Text>
    </Box>
  );
}

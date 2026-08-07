import React, { useEffect, useMemo, useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { ApiClient, DEFAULT_BASE_URL, type ModelConfig } from '../../api/client';
import { theme } from '../theme';

interface ProviderGroup {
  provider: string;
  models: Array<{ provider: string; model: string; base_url: string }>;
}

export function ModelManager({
  onClose,
  onModelChanged,
}: {
  onClose: () => void;
  onModelChanged: (model: string) => void;
}) {
  const [config, setConfig] = useState<ModelConfig | null>(null);
  const [view, setView] = useState<'providers' | 'models'>('providers');
  const [providerIndex, setProviderIndex] = useState(0);
  const [modelIndex, setModelIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const providers: ProviderGroup[] = useMemo(() => {
    if (!config) return [];
    const grouped = new Map<string, ProviderGroup>();
    for (const item of config.available) {
      const existing = grouped.get(item.provider);
      if (existing) {
        existing.models.push(item);
      } else {
        grouped.set(item.provider, {
          provider: item.provider,
          models: [item],
        });
      }
    }
    return Array.from(grouped.values());
  }, [config]);

  useEffect(() => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    client
      .getModelConfig()
      .then((state) => {
        setConfig(state);
        const initialProvider = state.available.findIndex(
          (item) => item.provider === state.provider,
        );
        if (initialProvider >= 0) {
          setProviderIndex(initialProvider);
        }
      })
      .catch((err: unknown) => {
        setError(String(err));
      })
      .finally(() => setLoading(false));
  }, []);

  const selectedProvider = providers[providerIndex];
  const selectedModel = selectedProvider?.models[modelIndex];

  const switchModel = async (provider: string, model: string) => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    setBusy(true);
    setNotice('');
    try {
      const state = await client.setModelConfig({ provider, model });
      setConfig(state);
      onModelChanged(state.model);
      setNotice(`已切换: ${state.provider} / ${state.model}`);
      onClose();
    } catch (err: unknown) {
      setNotice(`切换失败: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  };

  useInput((_input, key) => {
    if (busy) return;
    if (key.escape) {
      if (view === 'models') {
        setView('providers');
        return;
      }
      onClose();
      return;
    }
    if (key.upArrow) {
      if (view === 'providers') {
        setProviderIndex((index) => Math.max(0, index - 1));
      } else if (selectedProvider) {
        setModelIndex((index) => Math.max(0, index - 1));
      }
      return;
    }
    if (key.downArrow) {
      if (view === 'providers') {
        setProviderIndex((index) => Math.min(providers.length - 1, index + 1));
      } else if (selectedProvider) {
        setModelIndex((index) => Math.min(selectedProvider.models.length - 1, index + 1));
      }
      return;
    }
    if (key.return) {
      if (view === 'providers' && selectedProvider) {
        setModelIndex(0);
        setView('models');
        return;
      }
      if (view === 'models' && selectedProvider && selectedModel) {
        void switchModel(selectedProvider.provider, selectedModel.model);
      }
    }
  });

  return (
    <Box flexDirection="column" width="100%" backgroundColor={theme.surface} paddingX={1}>
      <Text bold color={theme.teal}>
        {view === 'providers' ? '模型管理' : `模型管理 · ${selectedProvider?.provider ?? ''}`}
      </Text>
      {config ? (
        <Text color={theme.blue}>
          当前模型：{config.provider} / {config.model}
        </Text>
      ) : null}
      <Text bold>{view === 'providers' ? 'Provider：' : 'Model：'}</Text>
      {loading ? (
        <Text dimColor>正在加载模型配置…</Text>
      ) : error ? (
        <Text color={theme.red}>读取失败: {error}</Text>
      ) : view === 'providers' ? (
        <Box flexDirection="column">
          {providers.map((group, index) => (
            <Text key={group.provider} color={index === providerIndex ? theme.teal : theme.text}>
              {index === providerIndex ? '▸ ' : '  '}
              {group.provider}
              <Text dimColor>  {group.models.length} 个模型</Text>
            </Text>
          ))}
        </Box>
      ) : (
        <Box flexDirection="column">
          {(selectedProvider?.models ?? []).map((item, index) => (
            <Text key={item.model} color={index === modelIndex ? theme.teal : theme.text}>
              {index === modelIndex ? '▸ ' : '  '}
              {item.model}
              {item.provider === config?.provider && item.model === config?.model ? (
                <Text color={theme.green}>  ✓ 当前</Text>
              ) : null}
            </Text>
          ))}
        </Box>
      )}
      {notice ? (
        <Text color={notice.startsWith('已切换') ? theme.green : theme.red}>{notice}</Text>
      ) : null}
      <Text dimColor>
        {view === 'providers' ? '[↑/↓] 选择 [enter] 查看模型 [esc] 关闭' : '[↑/↓] 选择 [enter] 切换 [esc] 返回'}
      </Text>
    </Box>
  );
}

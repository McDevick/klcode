import React, { useEffect, useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { ApiClient, DEFAULT_BASE_URL } from '../../api/client';
import { theme } from '../theme';

type View = 'menu' | 'provider-add' | 'provider-list' | 'key-set' | 'model-set' | 'model-show';

interface MenuItem {
  label: string;
  desc: string;
  view: View;
}

const MENU: MenuItem[] = [
  { label: 'provider list', desc: '查看已注册 provider', view: 'provider-list' },
  { label: 'provider add', desc: '注册 openai-compatible provider', view: 'provider-add' },
  { label: 'key set', desc: '设置 API Key', view: 'key-set' },
  { label: 'model set', desc: '切换全局模型', view: 'model-set' },
  { label: 'model show', desc: '查看当前模型', view: 'model-show' },
];

interface FieldDef {
  label: string;
  secret?: boolean;
  defaultValue?: string;
}

const FORMS: Record<'provider-add' | 'key-set' | 'model-set', FieldDef[]> = {
  'provider-add': [
    { label: 'name' },
    { label: 'type', defaultValue: 'openai-compatible' },
    { label: 'base_url' },
    { label: 'default_model' },
  ],
  'key-set': [
    { label: 'ref' },
    { label: 'secret', secret: true },
  ],
  'model-set': [
    { label: 'provider' },
    { label: 'model (可选，留空用 provider 默认)' },
  ],
};

export function ConfigWizard({
  onClose,
  onMessage,
}: {
  onClose: () => void;
  onMessage: (content: string, kind: 'text' | 'info' | 'error' | 'done') => void;
}) {
  const [view, setView] = useState<View>('menu');
  const [menuIndex, setMenuIndex] = useState(0);
  const [fields, setFields] = useState<FieldDef[]>([]);
  const [values, setValues] = useState<string[]>([]);
  const [fieldIndex, setFieldIndex] = useState(0);
  const [cursorVisible, setCursorVisible] = useState(true);
  const [loading, setLoading] = useState(false);
  const [listContent, setListContent] = useState('');

  useEffect(() => {
    const timer = setInterval(() => setCursorVisible((current) => !current), 500);
    return () => clearInterval(timer);
  }, []);

  const enterForm = (nextView: 'provider-add' | 'key-set' | 'model-set') => {
    const form = FORMS[nextView];
    setView(nextView);
    setFields(form);
    setValues(form.map((field) => field.defaultValue ?? ''));
    setFieldIndex(0);
  };

  const backToMenu = () => {
    setView('menu');
    setMenuIndex(0);
    setFields([]);
    setValues([]);
    setListContent('');
  };

  const loadList = (nextView: 'provider-list' | 'model-show') => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    setView(nextView);
    setLoading(true);
    setListContent('');
    const request =
      nextView === 'provider-list'
        ? client.listProviders().then((providers) =>
            providers.map((p) => `  ${p.name}: ${p.type}${p.base_url ? ` (${p.base_url})` : ''}`).join('\n'),
          )
        : client.getModelConfig().then((state) => {
            const lines = [`  provider: ${state.provider}`, `  model: ${state.model}`];
            if (state.available.length > 0) {
              lines.push('  可用:');
              lines.push(...state.available.map((item) => `    ${item.provider}: ${item.model}`));
            }
            return lines.join('\n');
          });
    request
      .then((content) => {
        setListContent(content || '  (空)');
        setLoading(false);
      })
      .catch((error: unknown) => {
        setListContent(`  读取失败: ${String(error)}`);
        setLoading(false);
      });
  };

  const submit = () => {
    const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
    const done = () => {
      backToMenu();
    };
    if (view === 'provider-add') {
      const [name, type, baseUrl, model] = values;
      if (!name || !baseUrl || !model) {
        onMessage('provider add 失败: name/base_url/default_model 不能为空', 'error');
        backToMenu();
        return;
      }
      client
        .addProvider({ name, type: type || 'openai-compatible', base_url: baseUrl, default_model: model })
        .then((result) => {
          onMessage(`provider 已注册: ${result.name} (${result.default_model})`, 'done');
          done();
        })
        .catch((error: unknown) => {
          onMessage(`provider 注册失败: ${String(error)}`, 'error');
          done();
        });
      return;
    }
    if (view === 'key-set') {
      const [ref, secret] = values;
      if (!ref || !secret) {
        onMessage('key set 失败: ref 和 secret 不能为空', 'error');
        backToMenu();
        return;
      }
      client
        .setKey(ref, secret)
        .then((result) => {
          onMessage(`密钥已配置: ${ref} (${result.configured ? 'ok' : '未生效'})`, 'done');
          done();
        })
        .catch((error: unknown) => {
          onMessage(`密钥配置失败: ${String(error)}`, 'error');
          done();
        });
      return;
    }
    if (view === 'model-set') {
      const [provider, model] = values;
      if (!provider) {
        onMessage('model set 失败: provider 不能为空', 'error');
        backToMenu();
        return;
      }
      client
        .setModelConfig(model ? { provider, model } : { provider })
        .then((state) => {
          onMessage(`模型已切换: ${state.provider} / ${state.model}`, 'done');
          done();
        })
        .catch((error: unknown) => {
          onMessage(`模型切换失败: ${String(error)}`, 'error');
          done();
        });
      return;
    }
  };

  useInput((input, key) => {
    if (view === 'menu') {
      if (key.upArrow) {
        setMenuIndex((index) => Math.max(0, index - 1));
        return;
      }
      if (key.downArrow) {
        setMenuIndex((index) => Math.min(MENU.length - 1, index + 1));
        return;
      }
      if (key.return) {
        const item = MENU[menuIndex];
        if (item.view === 'provider-add' || item.view === 'key-set' || item.view === 'model-set') {
          enterForm(item.view);
        } else if (item.view === 'provider-list' || item.view === 'model-show') {
          loadList(item.view);
        }
        return;
      }
      if (key.escape) {
        onClose();
        return;
      }
      return;
    }
    if (view === 'provider-list' || view === 'model-show') {
      if (key.escape || key.return || input === ' ') {
        backToMenu();
      }
      return;
    }
    // 表单输入
    if (key.escape) {
      backToMenu();
      return;
    }
    if (key.return) {
      if (fieldIndex < fields.length - 1) {
        setFieldIndex((index) => index + 1);
      } else {
        submit();
      }
      return;
    }
    if (key.backspace || key.delete) {
      setValues((current) =>
        current.map((value, index) => (index === fieldIndex ? value.slice(0, -1) : value)),
      );
      return;
    }
    if (input.length > 0) {
      setValues((current) =>
        current.map((value, index) => (index === fieldIndex ? value + input : value)),
      );
    }
  });

  const title =
    view === 'menu'
      ? '配置向导'
      : view === 'provider-add'
        ? '注册 provider'
        : view === 'provider-list'
          ? 'provider 列表'
          : view === 'key-set'
            ? '设置 API Key'
            : view === 'model-set'
              ? '切换全局模型'
              : '当前模型';

  const mask = (value: string, secret: boolean | undefined) =>
    secret ? '•'.repeat(value.length) : value;

  return (
    <Box paddingX={1}>
      <Box
        borderStyle="round"
        borderColor={theme.surfaceAlt}
        backgroundColor={theme.surface}
        paddingX={1}
        paddingY={1}
        flexDirection="column"
        width="100%"
      >
        <Text bold color={theme.teal}>
          {title}
        </Text>
        {view === 'menu' ? (
          <Box flexDirection="column" paddingTop={1}>
            {MENU.map((item, index) => (
              <Text key={item.label} color={index === menuIndex ? theme.teal : theme.text}>
                {index === menuIndex ? '▸ ' : '  '}
                {item.label}
                <Text dimColor>  {item.desc}</Text>
              </Text>
            ))}
            <Box paddingTop={1}>
              <Text dimColor>[↑/↓] 选择 [enter] 进入 [esc] 关闭</Text>
            </Box>
          </Box>
        ) : null}
        {view === 'provider-list' || view === 'model-show' ? (
          <Box flexDirection="column" paddingTop={1}>
            {loading ? (
              <Text dimColor>  加载中...</Text>
            ) : (
              <Text dimColor>{listContent}</Text>
            )}
            <Box paddingTop={1}>
              <Text dimColor>[任意键] 返回</Text>
            </Box>
          </Box>
        ) : null}
        {view === 'provider-add' || view === 'key-set' || view === 'model-set' ? (
          <Box flexDirection="column" paddingTop={1}>
            {fields.map((field, index) => {
              const active = index === fieldIndex;
              const display = mask(values[index], field.secret);
              return (
                <Text key={field.label} color={active ? theme.text : theme.textDim}>
                  <Text color={active ? theme.yellow : theme.textDim}>{field.label}: </Text>
                  {display}
                  {active && cursorVisible ? '▍' : ''}
                </Text>
              );
            })}
            <Box paddingTop={1}>
              <Text dimColor>[enter] 下一项/提交 [backspace] 删除 [esc] 返回</Text>
            </Box>
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}

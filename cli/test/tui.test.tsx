import { expect, test, vi } from 'vitest';
import { render } from 'ink-testing-library';
import React from 'react';
import { App } from '../src/tui/app';
import { UserBubble, AgentBubble } from '../src/tui/components/messages';
import { StatusCard } from '../src/tui/components/status-card';
import type { RunningTask } from '../src/tui/types';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onmessage: ((event: { data: string }) => void) | null = null;
  sent: string[] = [];
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  addEventListener(event: string, callback: () => void) {
    if (event === 'open') {
      callback();
    }
  }
}

function stubWebSocket() {
  const original = globalThis.WebSocket;
  (globalThis as { WebSocket: unknown }).WebSocket = FakeWebSocket;
  return () => {
    (globalThis as { WebSocket: unknown }).WebSocket = original;
    FakeWebSocket.instances = [];
  };
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitFor(
  condition: () => boolean,
  timeout = 2000,
  interval = 20,
): Promise<void> {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (condition()) {
      return;
    }
    await sleep(interval);
  }
}

const sessionResponse = {
  ok: true,
  status: 200,
  json: async () => ({ id: 's1', workspace: process.cwd(), name: 'default', status: 'active' }),
};

const modelConfigResponse = {
  ok: true,
  status: 200,
  json: async () => ({
    provider: 'mock',
    model: 'mock-model',
    available: [{ provider: 'mock', model: 'mock-model', base_url: '' }],
  }),
};

// App 初始化：listSessions（无空会话）→ createSession，随后 getModelConfig。
// URL 分发 mock 按请求路径/方法返回，避免依赖请求顺序。
const listSessionsEmpty = {
  ok: true,
  status: 200,
  json: async () => [],
};

function urlFetchMock() {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions') && method === 'GET') return listSessionsEmpty;
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    return { ok: true, status: 200, json: async () => ({}) };
  });
}

function taskFetchMocks() {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions') && method === 'GET') return listSessionsEmpty;
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    if (url.includes('/abort')) {
      return { ok: true, status: 200, json: async () => ({ status: 'canceled' }) };
    }
    if (url.includes('/run')) {
      return { ok: true, status: 202, json: async () => ({ status: 'running' }) };
    }
    if (url.includes('/api/v1/tasks')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ id: 't1', session_id: 's1', description: 'hello', status: 'pending' }),
      };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  });
}

function emit(socket: FakeWebSocket, payload: Record<string, unknown>) {
  socket.onmessage?.({ data: JSON.stringify({ task_id: 't1', ...payload }) });
}

test('user bubble renders right aligned content', () => {
  const { lastFrame } = render(<UserBubble content="hello world" />);
  expect(lastFrame()).toContain('hello world');
});

test('agent bubble renders markdown content', () => {
  const { lastFrame } = render(<AgentBubble content="**bold** and plain" kind="text" />);
  expect(lastFrame()).toContain('bold');
  expect(lastFrame()).toContain('plain');
});

test('status card shows spinner metrics and tool calls', () => {
  const running: RunningTask = {
    taskId: 't1',
    startedAt: Date.now(),
    steps: 12,
    toolCalls: [{ name: 'read_file', args: '{"path":"a.ts"}', summary: 'ok' }],
  };
  const { lastFrame, unmount } = render(<StatusCard running={running} />);
  try {
    expect(lastFrame()).toContain('thinking');
    expect(lastFrame()).toContain('12 steps');
    expect(lastFrame()).toContain('read_file');
    expect(lastFrame()).toContain('ok');
  } finally {
    unmount();
  }
});

test('app creates a session and renders ready message', async () => {
  const fetchMock = urlFetchMock();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    expect(lastFrame()).toContain('会话 s1 已就绪');
    expect(lastFrame()).toContain('KLCODE');
    expect(lastFrame()).toContain('●');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app submits a task and streams events into messages', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('hello'));

    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      'http://127.0.0.1:8700/api/v1/tasks',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      'http://127.0.0.1:8700/api/v1/tasks/t1/run',
      expect.objectContaining({ method: 'POST' }),
    );

    await waitFor(() => FakeWebSocket.instances.length > 0);
    const socket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    emit(socket, { event: 'loop_start', payload: { task: 'hello' } });
    emit(socket, { event: 'tool_result', payload: { tool: 'run_command', ok: true, error: null } });
    emit(socket, { event: 'task_end', status: 'succeeded' });
    await waitFor(() => (lastFrame() ?? '').includes('任务完成: succeeded'));
    expect(lastFrame()).toContain('任务完成: succeeded');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('slash menu opens on / and arrow selection fills the input', async () => {
  const fetchMock = urlFetchMock();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/');
    // 命令面板出现（测试视口较矮，断言窗口底部靠输入框的可见项）
    await waitFor(() => (lastFrame() ?? '').includes('暂停任务'));
    expect(lastFrame()).toContain('暂停任务');

    // 滚动窗口：ArrowDown 一路到 /exit（index 9）后菜单滚动显示底部命令
    for (let i = 0; i < 9; i += 1) {
      stdin.write('[B');
    }
    await sleep(30);
    expect(lastFrame()).toContain('退出 TUI');

    // ArrowDown 回到 index 1（/session），Enter 填入输入框
    for (let i = 0; i < 8; i += 1) {
      stdin.write('[A');
    }
    await sleep(30);
    stdin.write('\r');
    await sleep(30);
    expect(lastFrame()).toContain('/session ');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app shows approval bar and sends decision on a', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => FakeWebSocket.instances.length > 0);

    const socket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    emit(socket, {
      event: 'approval_request',
      action_id: 'a1',
      tool: 'run_command',
      args: { command: 'rm -rf /' },
      level: 'critical',
    });
    await waitFor(() => (lastFrame() ?? '').includes('审批请求'));
    expect(lastFrame()).toContain('rm -rf /');

    stdin.write('a');
    await sleep(50);
    const decisionSocket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    expect(decisionSocket.sent.some((data) => data.includes('"approve"'))).toBe(true);
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app runs /status slash command', async () => {
  const fetchMock = urlFetchMock();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/status');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('session: s1'));
    expect(lastFrame()).toContain('session: s1');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app aborts the current task via the api', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('hello'));
    stdin.write('/abort');
    stdin.write('\r');
    await waitFor(() => fetchMock.mock.calls.length >= 7);
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      'http://127.0.0.1:8700/api/v1/tasks/t1/abort',
      expect.objectContaining({ method: 'POST' }),
    );
    await waitFor(() => (lastFrame() ?? '').includes('任务状态: canceled'));
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('typing a full slash command executes it instead of filling the menu', async () => {
  const fetchMock = urlFetchMock();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const exitSpy = vi.spyOn(process, 'exit').mockImplementation(() => undefined as never);
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/exit');
    stdin.write('\r');
    await sleep(50);
    expect(exitSpy).toHaveBeenCalledWith(0);
  } finally {
    exitSpy.mockRestore();
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('slash menu filters commands by typed prefix and completes on enter', async () => {
  const fetchMock = urlFetchMock();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    // /ab 只匹配 /abort（过滤），非精确匹配 → Enter 补全
    stdin.write('/ab');
    await sleep(30);
    stdin.write('\r');
    await sleep(30);
    expect(lastFrame()).toContain('/abort ');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app exits on /exit', async () => {
  const fetchMock = urlFetchMock();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const exitSpy = vi.spyOn(process, 'exit').mockImplementation(() => undefined as never);
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/exit');
    stdin.write('\r');
    await sleep(50);
    expect(exitSpy).toHaveBeenCalledWith(0);
  } finally {
    exitSpy.mockRestore();
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app /model shows current and available models', async () => {
  // App 初始化：createSession + getModelConfig；第 3 次 fetch 是 /model 读取
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(sessionResponse)
    .mockResolvedValueOnce(modelConfigResponse)
    .mockResolvedValueOnce(modelConfigResponse);
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/model');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('当前: mock / mock-model'));
    expect(lastFrame()).toContain('当前: mock / mock-model');
    expect(lastFrame()).toContain('mock: mock-model');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app /model <provider> switches model via api', async () => {
  // App 初始化：createSession + getModelConfig；第 3 次 fetch 是 /model 切换（POST）
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(sessionResponse)
    .mockResolvedValueOnce(modelConfigResponse)
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        provider: 'deepseek',
        model: 'deepseek-chat',
        available: [{ provider: 'deepseek', model: 'deepseek-chat', base_url: 'https://api.deepseek.com/v1' }],
      }),
    });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/model deepseek');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('模型已切换: deepseek / deepseek-chat'));
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8700/api/v1/config/model',
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('"provider":"deepseek"') }),
    );
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app /config opens the config wizard menu', async () => {
  const fetchMock = urlFetchMock();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/config');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('配置向导'));
    expect(lastFrame()).toContain('provider add');
    expect(lastFrame()).toContain('key set');
    expect(lastFrame()).toContain('model set');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app config wizard lists providers and esc returns to menu', async () => {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions') && method === 'GET') return listSessionsEmpty;
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    if (url.includes('/api/v1/providers')) {
      return {
        ok: true,
        status: 200,
        json: async () => [
          { name: 'mock', type: 'mock' },
          { name: 'deepseek', type: 'openai-compatible', base_url: 'https://api.deepseek.com/v1' },
        ],
      };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/config');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('配置向导'));
    await sleep(200); // 等待 ConfigWizard 的 useInput 订阅建立，避免首个按键丢失
    stdin.write('\r'); // 第一项：provider list
    await waitFor(() => (lastFrame() ?? '').includes('deepseek'));
    expect(lastFrame()).toContain('deepseek');
    stdin.write('\u001b'); // esc 返回菜单
    await waitFor(() => (lastFrame() ?? '').includes('provider add'));
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app config wizard adds a provider via form', async () => {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions') && method === 'GET') return listSessionsEmpty;
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    if (url.includes('/api/v1/providers')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          name: 'acme',
          type: 'openai-compatible',
          base_url: 'http://example.com/v1',
          default_model: 'model-x',
        }),
      };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/config');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('配置向导'));
    await sleep(200); // 等待 ConfigWizard 的 useInput 订阅建立
    stdin.write('[B');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('注册 provider'));
    stdin.write('acme');
    await sleep(80);
    stdin.write('\r');
    await sleep(80);
    stdin.write('\r');
    await sleep(80);
    stdin.write('http://example.com/v1');
    await sleep(80);
    stdin.write('\r');
    await sleep(80);
    stdin.write('model-x');
    await sleep(80);
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('provider 已注册'), 3000);
    expect(fetchMock.mock.calls.some((c) => c[0] === 'http://127.0.0.1:8700/api/v1/providers')).toBe(true);
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});



test('mouse wheel up scrolls to history and down returns', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    // 发 14 条消息制造可滚动内容
    for (let i = 0; i < 14; i += 1) {
      stdin.write(`消息${i}`);
      stdin.write('\r');
      await sleep(50);
    }
    await waitFor(() => (lastFrame() ?? '').includes('消息13'));
    // 滚轮上滚（SGR 按钮 64）→ 查看历史，最新消息被隐藏
    stdin.write('\x1b[<64;5;5M');
    await sleep(100);
    expect(lastFrame()).not.toContain('消息13');
    // 滚轮下滚（SGR 按钮 65）→ 回到最新
    stdin.write('\x1b[<65;5;5M');
    await sleep(100);
    expect(lastFrame()).toContain('消息13');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('mouse click sequence is not injected into input', async () => {
  const fetchMock = urlFetchMock();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('\x1b[<0;37;12M'); // 鼠标左键点击序列
    await sleep(100);
    const inputLine = (lastFrame() ?? '').split('\n').find((l) => l.includes('>'));
    expect(inputLine).toContain('> ');
    expect(inputLine ?? '').not.toContain('<0;37');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('wheel does not scroll conversation while config wizard is open', async () => {
  const fetchMock = urlFetchMock();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('你好');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('你好'));
    stdin.write('/config');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('配置向导'));
    stdin.write('\x1b[<64;5;5M'); // 滚轮上滚
    await sleep(150);
    expect(lastFrame()).toContain('你好');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('wheel up with few messages keeps at least the earliest visible', async () => {
  const fetchMock = urlFetchMock();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('第一条');
    stdin.write('\r');
    await sleep(50);
    stdin.write('第二条');
    stdin.write('\r');
    await sleep(50);
    await waitFor(() => (lastFrame() ?? '').includes('第二条'));
    // 滚轮上滚一次（消息少时步长为 1）：平滑滚动，对话仍可见
    stdin.write('\x1b[<64;5;5M');
    await sleep(100);
    expect(lastFrame()).toContain('第一条');
    // 滚到最早：至少保留 1 条消息，不出现空白对话
    for (let i = 0; i < 5; i += 1) {
      stdin.write('\x1b[<64;5;5M');
      await sleep(50);
    }
    expect(lastFrame()).toContain('会话 s1 已就绪');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app reuses an existing empty active session instead of creating one', async () => {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions') && method === 'GET') {
      return {
        ok: true,
        status: 200,
        json: async () => [
          { id: 's9', workspace: process.cwd(), name: 'old', status: 'active', task_count: 0 },
          { id: 's8', workspace: process.cwd(), name: 'busy', status: 'active', task_count: 3 },
        ],
      };
    }
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('复用会话 s9'));
    expect(lastFrame()).toContain('复用会话 s9');
    // 复用了空会话，不应再发起 createSession
    expect(fetchMock.mock.calls.filter((c) => (c[1] as RequestInit)?.method === 'POST')).toHaveLength(0);
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app shows model final answer from task_end result', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => FakeWebSocket.instances.length > 0);
    const socket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    emit(socket, { event: 'task_end', status: 'succeeded', result: 'DONE: 这是模型的最终回答' });
    await waitFor(() => (lastFrame() ?? '').includes('这是模型的最终回答'));
    expect(lastFrame()).toContain('这是模型的最终回答');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app shows agent message event and failure reason', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => FakeWebSocket.instances.length > 0);
    const socket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    emit(socket, { event: 'agent_message', payload: { text: '我先看一下目录结构' } });
    await waitFor(() => (lastFrame() ?? '').includes('我先看一下目录结构'));
    emit(socket, { event: 'task_end', status: 'failed', result: 'MAX_ITERATIONS' });
    await waitFor(() => (lastFrame() ?? '').includes('任务失败: MAX_ITERATIONS'));
    expect(lastFrame()).toContain('任务失败: MAX_ITERATIONS');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

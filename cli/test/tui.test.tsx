import { expect, test, vi } from 'vitest';
import { render } from 'ink-testing-library';
import React from 'react';
import { App } from '../src/tui/app';
import { UserBubble, AgentBubble, ToolCallLine } from '../src/tui/components/messages';
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

function hasTaskSocket(): boolean {
  return FakeWebSocket.instances.some((socket) => socket.url.includes('/ws/tasks/'));
}

function taskSocket(): FakeWebSocket {
  const socket = FakeWebSocket.instances.find((item) => item.url.includes('/ws/tasks/'));
  if (socket === undefined) throw new Error('task socket not found');
  return socket;
}

function latestTaskSocket(): FakeWebSocket {
  const sockets = FakeWebSocket.instances.filter((item) =>
    item.url.includes('/ws/tasks/'),
  );
  const socket = sockets[sockets.length - 1];
  if (socket === undefined) throw new Error('task socket not found');
  return socket;
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
    max_context: 20000,
    available: [{ provider: 'mock', model: 'mock-model', base_url: '', max_context: 20000 }],
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

test('agent bubble renders inline markdown in headings and lists', () => {
  const { lastFrame } = render(
    <AgentBubble
      content="## **bold heading**\n\n1. **bold item**\n\n> **bold quote**"
      kind="text"
    />,
  );
  expect(lastFrame()).toContain('bold heading');
  expect(lastFrame()).toContain('bold item');
  expect(lastFrame()).toContain('bold quote');
  expect(lastFrame()).not.toContain('**');
});

test('tool line renders readable args and status label', () => {
  const { lastFrame, unmount } = render(
    <ToolCallLine
      tool={{
        name: 'read_file',
        args: '"src/a.ts"',
        summary: 'ok',
        ok: true,
      }}
    />,
  );
  try {
    expect(lastFrame()).toContain('[Tool]: read_file');
    expect(lastFrame()).toContain('read_file("src/a.ts")');
    expect(lastFrame()).toContain('✓');
  } finally {
    unmount();
  }
});

test('tool line renders approval as warning', () => {
  const { lastFrame, unmount } = render(
    <ToolCallLine
      tool={{
        name: 'delete_file',
        args: '"tmp/a.log"',
        summary: 'warning: requires_approval',
        ok: false,
        warning: true,
      }}
    />,
  );
  try {
    expect(lastFrame()).toContain('warning: requires_approval');
    expect(lastFrame()).not.toContain('?');
    expect(lastFrame()).not.toContain('✗');
  } finally {
    unmount();
  }
});

test('tool line renders task_manage checklist', () => {
  const { lastFrame, unmount } = render(
    <ToolCallLine
      tool={{
        name: 'task_manage',
        args: 'action="list"',
        summary: '',
        ok: true,
        taskItems: [
          { title: '读取文件', done: false },
          { title: '写入文件', done: true },
        ],
      }}
    />,
  );
  try {
    expect(lastFrame()).toContain('[ ] 读取文件');
    expect(lastFrame()).toContain('[✓] 写入文件');
  } finally {
    unmount();
  }
});

test('status card shows thinking timer and step count', () => {
  const running: RunningTask = {
    taskId: 't1',
    startedAt: Date.now(),
    steps: 12,
  };
  const { lastFrame, unmount } = render(<StatusCard running={running} />);
  try {
    expect(lastFrame()).toContain('thinking');
    expect(lastFrame()).toContain('12 次工具调用');
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

    await waitFor(() => hasTaskSocket());
    const socket = taskSocket();
    emit(socket, { event: 'loop_start', payload: { task: 'hello' } });
    emit(socket, {
      event: 'tool_result',
      payload: {
        tool: 'run_command',
        ok: true,
        error: null,
        args: { command: 'echo hi' },
        output: '{"exit_code":0,"stdout":"hi","stderr":""}',
      },
    });
    // 工具调用显示命令与结果摘要
    await waitFor(() => (lastFrame() ?? '').includes('run_command("echo hi")'));
    expect(lastFrame()).toContain('run_command("echo hi")');
    expect(lastFrame()).toContain('exit 0 · hi');
    expect(lastFrame()).toContain('[Tool]: run_command');
    emit(socket, { event: 'task_end', status: 'succeeded' });
    await waitFor(() => (lastFrame() ?? '').includes('任务完成: succeeded'));
    expect(lastFrame()).toContain('任务完成: succeeded');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app shows feedback_generation event', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => hasTaskSocket());
    const socket = taskSocket();
    emit(socket, {
      event: 'feedback_generation',
      payload: {
        tool: 'run_tests',
        category: 'test_failure',
        summary: 'assert failed: test_app_basic',
      },
    });
    await waitFor(() =>
      (lastFrame() ?? '').includes(
        '[Feedback] run_tests: test_failure: assert failed: test_app_basic',
      ),
    );
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app truncates long feedback summary with ellipsis', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => hasTaskSocket());
    const socket = taskSocket();
    const summary = 'x'.repeat(200);
    emit(socket, {
      event: 'feedback_generation',
      payload: {
        tool: 'run_tests',
        category: 'test_failure',
        summary,
      },
    });
    await waitFor(() =>
      (lastFrame() ?? '').includes('[Feedback] run_tests: test_failure: '),
    );
    expect(lastFrame()).toContain('...');
    expect(lastFrame() ?? '').not.toContain('x'.repeat(200));
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
    await waitFor(() => (lastFrame() ?? '').includes('/context'));
    expect(lastFrame()).toContain('/context');
    const menuFrame = lastFrame() ?? '';
    expect(menuFrame.indexOf('/context')).toBeLessThan(menuFrame.indexOf('> '));

    // 滚动窗口：ArrowDown 一路到 /exit（index 16，共 17 项）后菜单滚动显示底部命令
    for (let i = 0; i < 16; i += 1) {
      stdin.write('[B');
    }
    await sleep(30);
    expect(lastFrame()).toContain('退出 TUI');

    // ArrowDown 回到 index 0（/session），Enter 填入输入框
    for (let i = 0; i < 16; i += 1) {
      stdin.write('[A');
    }
    await sleep(30);
    stdin.write('\r');
    await sleep(30);
    expect(lastFrame()).toContain('/session');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app /skills opens a command-style skill menu', async () => {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/skills') && method === 'GET') {
      return {
        ok: true,
        status: 200,
        json: async () => [
          { name: 'leetcode', description: '解决 LeetCode C++ 题目' },
          { name: 'python', description: 'Python 开发' },
        ],
      };
    }
    if (url.includes('/api/v1/sessions') && method === 'GET') return listSessionsEmpty;
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/skills');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('leetcode'));
    expect(lastFrame()).toContain('解决 LeetCode C++ 题目');
    expect(lastFrame()).toContain('python');
    expect(lastFrame()).toContain('▸');

    stdin.write('\u001b');
    await waitFor(() => !(lastFrame() ?? '').includes('leetcode'));
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app /mcp opens manager and deletes selected server', async () => {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/mcp/demo') && method === 'DELETE') {
      return { ok: true, status: 204 };
    }
    if (url.includes('/api/v1/mcp') && method === 'GET') {
      return {
        ok: true,
        status: 200,
        json: async () => [
          {
            name: 'demo',
            url: 'http://localhost:9999',
            tools: [
              {
                name: 'mcp_demo_echo',
                remote_name: 'echo',
                description: 'echo text',
              },
            ],
          },
        ],
      };
    }
    if (url.includes('/api/v1/sessions') && method === 'GET') return listSessionsEmpty;
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/mcp');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('demo'));
    expect(lastFrame() ?? '').not.toContain('mcp_demo_echo');

    stdin.write('d');
    await sleep(50);
    stdin.write('d');
    await waitFor(() => (lastFrame() ?? '').includes('已删除: demo'));
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8700/api/v1/mcp/demo',
      expect.objectContaining({ method: 'DELETE' }),
    );
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
    await waitFor(() => hasTaskSocket());

    const socket = taskSocket();
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
    const decisionSocket = latestTaskSocket();
    expect(decisionSocket.sent.some((data) => data.includes('"approve"'))).toBe(true);
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app handles nested approval_request payload', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => hasTaskSocket());
    const socket = taskSocket();
    emit(socket, {
      event: 'approval_request',
      payload: {
        action_id: 'a1',
        tool: 'run_command',
        args: { command: 'rm -rf /' },
        level: 'critical',
        timeout_seconds: 300,
      },
    });
    await waitFor(() => (lastFrame() ?? '').includes('run_command'));
    expect(lastFrame()).toContain('critical');
    stdin.write('a');
    await sleep(50);
    const decisionSocket = latestTaskSocket();
    expect(decisionSocket.sent.some((data) => data.includes('"approve"'))).toBe(true);
    expect(decisionSocket.sent.some((data) => data.includes('"a1"'))).toBe(true);
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app approval menu can select reject with arrows and enter', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => hasTaskSocket());
    const socket = taskSocket();
    emit(socket, {
      event: 'approval_request',
      action_id: 'a1',
      tool: 'run_command',
      args: { command: 'rm -rf /' },
      level: 'critical',
    });
    await waitFor(() => (lastFrame() ?? '').includes('审批请求'));
    stdin.write('\u001b[B');
    await sleep(50);
    stdin.write('\r');
    await sleep(50);
    const decisionSocket = latestTaskSocket();
    expect(decisionSocket.sent.some((data) => data.includes('"reject"'))).toBe(true);
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

test('app /context and /compact show context status', async () => {
  const contextStatus = {
    max_tokens: 20000,
    used_tokens: 5000,
    remaining_tokens: 15000,
    sections: [
      { name: 'system', tokens: 1000, percent: 5 },
      { name: 'memory', tokens: 2000, percent: 10 },
      { name: 'history', tokens: 2000, percent: 10 },
    ],
  };
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/context/compact') && method === 'POST') {
      return { ok: true, status: 200, json: async () => contextStatus };
    }
    if (url.includes('/context') && method === 'GET') {
      return { ok: true, status: 200, json: async () => contextStatus };
    }
    if (url.includes('/api/v1/sessions') && method === 'GET') return listSessionsEmpty;
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/context');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('上下文: 5000/20000 tokens'));
    expect(lastFrame()).toContain('剩余: 15000/20000 tokens');

    stdin.write('/compact');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('上下文已压缩'));
    expect(lastFrame()).toContain('Compacting...');
    expect(lastFrame()).toContain('剩余 15000/20000 tokens');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app /session opens manager and enter selects session', async () => {
  let sessionListCount = 0;
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions/s2/history') && method === 'GET') {
      return {
        ok: true,
        status: 200,
        json: async () => [{ type: 'agent', content: '旧会话历史', kind: 'text' }],
      };
    }
    if (url.includes('/api/v1/sessions') && method === 'GET') {
      sessionListCount += 1;
      return {
        ok: true,
        status: 200,
        json: async () =>
          sessionListCount === 1
            ? []
            : [
                {
                  id: 's2',
                  workspace: process.cwd(),
                  name: 'old',
                  status: 'active',
                },
              ],
      };
    }
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/session');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('会话管理'));
    await waitFor(() => (lastFrame() ?? '').includes('old'));
    expect(lastFrame()).toContain('[Enter]');
    expect(lastFrame()).toContain('Delete');
    expect(lastFrame()).toContain('Rename');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('旧会话历史'));
    stdin.write('/status');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('session: s2'));
    expect(lastFrame()).toContain('session: s2');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('session manager displays id once when name equals id', async () => {
  let listCount = 0;
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions') && method === 'GET') {
      listCount += 1;
      return {
        ok: true,
        status: 200,
        json: async () =>
          listCount === 1
            ? []
            : [{ id: 's2', workspace: process.cwd(), name: 's2', status: 'active' }],
      };
    }
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/session');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('s2'));
    expect(lastFrame()).not.toContain('s2 · s2');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app session manager renames selected session', async () => {
  let renamed = false;
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions') && method === 'GET') {
      return {
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 's2',
            workspace: process.cwd(),
            name: renamed ? 'new-name' : 'old',
            status: 'active',
          },
        ],
      };
    }
    if (url.includes('/api/v1/sessions/s2') && method === 'PATCH') {
      renamed = true;
      return {
        ok: true,
        status: 200,
        json: async () => ({ id: 's2', name: 'new-name' }),
      };
    }
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/session');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('old'));
    stdin.write('r');
    await sleep(50);
    stdin.write('new-name');
    await sleep(50);
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('new-name'));
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8700/api/v1/sessions/s2',
      expect.objectContaining({
        method: 'PATCH',
        body: expect.stringContaining('new-name'),
      }),
    );
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app session manager clicks create new session card', async () => {
  let postCount = 0;
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions') && method === 'GET') {
      return { ok: true, status: 200, json: async () => [] };
    }
    if (url.includes('/api/v1/sessions') && method === 'POST') {
      postCount += 1;
      const id = postCount === 1 ? 's1' : 's3';
      return {
        ok: true,
        status: 200,
        json: async () => ({ id, workspace: process.cwd(), name: id, status: 'active' }),
      };
    }
    if (url.includes('/config/model')) return modelConfigResponse;
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/session');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('会话管理'));
    stdin.write('\x1b[<0;60;22M');
    await waitFor(() => (lastFrame() ?? '').includes('该会话暂无历史消息'));
    expect(
      fetchMock.mock.calls.some(
        (call) =>
          String(call[0]).includes('/api/v1/sessions') &&
          ((call[1] as RequestInit | undefined)?.method ?? 'GET') === 'POST',
      ),
    ).toBe(true);
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app blocks a second task while one is running', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('thinking'));
    const taskPostsBefore = fetchMock.mock.calls.filter(
      (call) =>
        String(call[0]).includes('/api/v1/tasks') &&
        ((call[1] as RequestInit | undefined)?.method ?? 'GET') === 'POST',
    ).length;
    stdin.write('second');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('当前任务仍在运行'));
    const taskPostsAfter = fetchMock.mock.calls.filter(
      (call) =>
        String(call[0]).includes('/api/v1/tasks') &&
        ((call[1] as RequestInit | undefined)?.method ?? 'GET') === 'POST',
    ).length;
    expect(taskPostsAfter).toBe(taskPostsBefore);
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app disables mouse tracking on unmount after /mouse', async () => {
  const fetchMock = urlFetchMock();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const writeSpy = vi.spyOn(process.stdout, 'write').mockImplementation(() => true);
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/mouse');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('鼠标追踪: 开'));
    unmount();
    expect(writeSpy).toHaveBeenCalledWith('\x1b[?1000l\x1b[?1006l');
  } finally {
    writeSpy.mockRestore();
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

test('app /note appends instruction to current task', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => hasTaskSocket());
    stdin.write('/note 请先运行测试');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('已追加说明: 请先运行测试'));
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8700/api/v1/tasks/t1/instructions',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('请先运行测试'),
      }),
    );
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app /exit requires confirmation while task is running', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const exitSpy = vi.spyOn(process, 'exit').mockImplementation(() => undefined as never);
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => hasTaskSocket());

    stdin.write('/exit');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('再次输入 /exit 确认退出'));
    expect(exitSpy).not.toHaveBeenCalled();

    stdin.write('/exit');
    stdin.write('\r');
    await waitFor(() => exitSpy.mock.calls.length > 0);
    expect(exitSpy).toHaveBeenCalledWith(0);
  } finally {
    exitSpy.mockRestore();
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app command registry reports missing required args', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => hasTaskSocket());

    stdin.write('/note');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('缺少参数 说明'));
    expect(lastFrame()).toContain('/note <说明>');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app blocks management commands while task is running', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => hasTaskSocket());

    for (const command of ['/session', '/compact', '/connect']) {
      stdin.write(command);
      stdin.write('\r');
      await waitFor(() =>
        (lastFrame() ?? '').includes(`${command}: 当前状态不可用`),
      );
    }
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
    expect(lastFrame()).toContain('/abort');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('bracketed paste keeps multi-line input content', async () => {
  const fetchMock = urlFetchMock();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write(
      '\x1b[200~**输入：**n = 10, t = 2\r\n\r\n**输出：**10\r\n\r\n**解释：**\r\n10 的数位乘积为 0\x1b[201~',
    );
    await waitFor(() => (lastFrame() ?? '').includes('**输入：**n = 10, t = 2'));
    expect(lastFrame()).toContain('**解释：**');
    expect(lastFrame()).toContain('10 的数位乘积为 0');
    expect(lastFrame()).toContain('>');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('input supports cursor movement and in-place editing', async () => {
  const fetchMock = urlFetchMock();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));

    stdin.write('abc');
    await waitFor(() => (lastFrame() ?? '').includes('abc'));
    stdin.write('\x1b[D');
    await sleep(30);
    stdin.write('\x1b[D');
    await sleep(30);
    stdin.write('X');
    await waitFor(() => (lastFrame() ?? '').includes('aXbc'));

    stdin.write('\x1b[D');
    await sleep(30);
    stdin.write('\x7f');
    await waitFor(() => (lastFrame() ?? '').includes('Xbc'));

    stdin.write('\x1b[1~');
    await sleep(30);
    stdin.write('A');
    await waitFor(() => (lastFrame() ?? '').includes('AXbc'));
    stdin.write('\x1b[4~');
    await sleep(30);
    stdin.write('Z');
    await waitFor(() => (lastFrame() ?? '').includes('AXbcZ'));
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('input arrow keys move cursor between multiline lines', async () => {
  const fetchMock = urlFetchMock();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('\x1b[200~ab\ncd\x1b[201~');
    await waitFor(() => (lastFrame() ?? '').includes('cd'));

    stdin.write('\x1b[A');
    await sleep(30);
    stdin.write('X');
    await waitFor(() => (lastFrame() ?? '').includes('abX'));

    stdin.write('\x1b[B');
    await sleep(30);
    stdin.write('Y');
    await waitFor(() => (lastFrame() ?? '').includes('cdY'));
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

test('app /model opens provider/model manager', async () => {
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
    await waitFor(() => (lastFrame() ?? '').includes('模型管理'));
    expect(lastFrame()).toContain('当前模型：mock / mock-model');
    expect(lastFrame()).toContain('Provider：');
    expect(lastFrame()).toContain('mock');
    expect(lastFrame()).toContain('mock-model');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app /model manager switches model and updates header', async () => {
  const availableConfig = {
    provider: 'mock',
    model: 'mock-model',
    max_context: 20000,
    available: [
      { provider: 'mock', model: 'mock-model', base_url: '', max_context: 20000 },
      {
        provider: 'deepseek',
        model: 'deepseek-chat',
        base_url: 'https://api.deepseek.com/v1',
        max_context: 20000,
      },
    ],
  };
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions') && method === 'GET') return listSessionsEmpty;
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model') && method === 'GET') {
      return { ok: true, status: 200, json: async () => availableConfig };
    }
    if (url.includes('/config/model') && method === 'POST') {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          provider: 'deepseek',
          model: 'deepseek-chat',
          max_context: 20000,
          available: [
            {
              provider: 'deepseek',
              model: 'deepseek-chat',
              base_url: 'https://api.deepseek.com/v1',
              max_context: 20000,
            },
          ],
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
    stdin.write('/model');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('deepseek'));
    await sleep(100);

    stdin.write('\x1b[B');
    await sleep(50);
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('deepseek-chat'));
    expect(lastFrame()).toContain('Model：');
    stdin.write('\r');

    await waitFor(() => (lastFrame() ?? '').includes('model: deepseek-chat'));
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8700/api/v1/config/model',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"provider":"deepseek"'),
      }),
    );
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

test('app /connect lists configured providers', async () => {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions') && method === 'GET') return listSessionsEmpty;
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    if (url.includes('/api/v1/providers') && method === 'GET') {
      return {
        ok: true,
        status: 200,
        json: async () => [
          { name: 'mock', type: 'mock' },
          {
            name: 'deepseek',
            type: 'openai-compatible',
            base_url: 'https://api.deepseek.com/v1',
            credential_ref: 'deepseek',
          },
        ],
      };
    }
    if (url.includes('/api/v1/keys') && method === 'GET') {
      return { ok: true, status: 200, json: async () => ({ configured: ['deepseek'] }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/connect');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('API 连接'));
    expect(lastFrame()).toContain('deepseek');
    expect(lastFrame()).toContain('✓ 已配置');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app /connect ignores plaintext provider without credential_ref', async () => {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions') && method === 'GET') return listSessionsEmpty;
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    if (url.includes('/api/v1/providers') && method === 'GET') {
      return {
        ok: true,
        status: 200,
        json: async () => [
          { name: 'mock', type: 'mock' },
          {
            name: 'deepseek',
            type: 'openai-compatible',
            base_url: 'https://api.deepseek.com/v1',
            credential_ref: null,
          },
        ],
      };
    }
    if (url.includes('/api/v1/keys') && method === 'GET') {
      return { ok: true, status: 200, json: async () => ({ configured: ['deepseek'] }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/connect');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('deepseek'));
    expect(lastFrame()).toContain('未配置');
    expect(lastFrame() ?? '').not.toContain('✓ 已配置');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app /connect saves and overwrites provider api key', async () => {
  let configuredKeys: string[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions') && method === 'GET') return listSessionsEmpty;
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    if (url.includes('/api/v1/providers') && method === 'GET') {
      return {
        ok: true,
        status: 200,
        json: async () => [
          { name: 'mock', type: 'mock' },
          {
            name: 'deepseek',
            type: 'openai-compatible',
            base_url: 'https://api.deepseek.com/v1',
            credential_ref: 'deepseek',
          },
        ],
      };
    }
    if (url.includes('/api/v1/keys/deepseek') && method === 'POST') {
      configuredKeys = ['deepseek'];
      return { ok: true, status: 200, json: async () => ({ configured: true }) };
    }
    if (url.includes('/api/v1/keys') && method === 'GET') {
      return { ok: true, status: 200, json: async () => ({ configured: configuredKeys }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/connect');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('API 连接'));
    await waitFor(() => (lastFrame() ?? '').includes('deepseek'));
    await sleep(100);

    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('API Key for deepseek'));
    stdin.write('sk-first-secret');
    await sleep(50);
    expect(lastFrame() ?? '').not.toContain('sk-first-secret');
    expect(lastFrame()).toContain('•');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('已保存: deepseek'));

    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('API Key for deepseek'));
    stdin.write('sk-second-secret');
    await sleep(50);
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('已保存: deepseek'));

    const postCalls = fetchMock.mock.calls.filter(
      (call) =>
        String(call[0]).includes('/api/v1/keys/deepseek') &&
        (call[1] as RequestInit)?.method === 'POST',
    );
    expect(postCalls).toHaveLength(2);
    expect(JSON.parse(String((postCalls[0][1] as RequestInit).body))).toEqual({
      secret: 'sk-first-secret',
    });
    expect(JSON.parse(String((postCalls[1][1] as RequestInit).body))).toEqual({
      secret: 'sk-second-secret',
    });
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app /connect pastes into api key input', async () => {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions') && method === 'GET') return listSessionsEmpty;
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    if (url.includes('/api/v1/providers') && method === 'GET') {
      return {
        ok: true,
        status: 200,
        json: async () => [
          { name: 'mock', type: 'mock' },
          {
            name: 'deepseek',
            type: 'openai-compatible',
            base_url: 'https://api.deepseek.com/v1',
            credential_ref: 'deepseek',
          },
        ],
      };
    }
    if (url.includes('/api/v1/keys/deepseek') && method === 'POST') {
      return { ok: true, status: 200, json: async () => ({ configured: true }) };
    }
    if (url.includes('/api/v1/keys') && method === 'GET') {
      return { ok: true, status: 200, json: async () => ({ configured: ['deepseek'] }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/connect');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('API 连接'));
    await waitFor(() => (lastFrame() ?? '').includes('deepseek'));
    await sleep(100);
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('API Key for deepseek'));

    stdin.write('\x1b[200~sk-pasted-secret\x1b[201~');
    await waitFor(() => (lastFrame() ?? '').includes('•'));
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('已保存: deepseek'));

    const postCall = fetchMock.mock.calls.find(
      (call) =>
        String(call[0]).includes('/api/v1/keys/deepseek') &&
        (call[1] as RequestInit)?.method === 'POST',
    );
    expect(JSON.parse(String((postCall?.[1] as RequestInit)?.body))).toEqual({
      secret: 'sk-pasted-secret',
    });
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
    // 滚轮需先开启鼠标追踪（默认关闭以保持鼠标选择复制可用）
    stdin.write('/mouse');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('鼠标追踪: 开'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => hasTaskSocket());
    const socket = taskSocket();
    const lines = Array.from({ length: 30 }, (_, index) => `消息${index}`);
    emit(socket, { event: 'task_end', status: 'succeeded', result: lines.join('\n') });
    await waitFor(() => (lastFrame() ?? '').includes('消息29'));
    // 初始停在最新内容；上滚查看更早的行
    for (let i = 0; i < 3; i += 1) {
      stdin.write('\x1b[<64;5;5M');
      await sleep(30);
    }
    expect(lastFrame()).not.toContain('消息29');
    // 下滚回到最新
    for (let i = 0; i < 3; i += 1) {
      stdin.write('\x1b[<65;5;5M');
      await sleep(30);
    }
    expect(lastFrame()).toContain('消息29');
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

test('wheel does not scroll conversation while connect panel is open', async () => {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions') && method === 'GET') return listSessionsEmpty;
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    if (url.includes('/api/v1/providers') && method === 'GET') {
      return {
        ok: true,
        status: 200,
        json: async () => [
          { name: 'mock', type: 'mock' },
          {
            name: 'deepseek',
            type: 'openai-compatible',
            base_url: 'https://api.deepseek.com/v1',
            credential_ref: 'deepseek',
          },
        ],
      };
    }
    if (url.includes('/api/v1/keys') && method === 'GET') {
      return { ok: true, status: 200, json: async () => ({ configured: [] }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    // 开启鼠标追踪以注入滚轮事件
    stdin.write('/mouse');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('鼠标追踪: 开'));
    stdin.write('/connect');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('API 连接'));
    stdin.write('\x1b[<64;5;5M'); // 滚轮上滚
    await sleep(150);
    expect(lastFrame()).toContain('API 连接');
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
    // 开启鼠标追踪以注入滚轮事件
    stdin.write('/mouse');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('鼠标追踪: 开'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => hasTaskSocket());
    const socket = taskSocket();
    const lines = Array.from({ length: 10 }, (_, index) => `行${index}`);
    emit(socket, { event: 'task_end', status: 'succeeded', result: lines.join('\n') });
    await waitFor(() => (lastFrame() ?? '').includes('行9'));
    // 滚轮上滚一次：按行平滑滚动，仍能看到内容
    stdin.write('\x1b[<64;5;5M');
    await sleep(100);
    expect(lastFrame()).toContain('行');
    // 滚到最顶部：不出现空白对话
    for (let i = 0; i < 5; i += 1) {
      stdin.write('\x1b[<64;5;5M');
      await sleep(50);
    }
    expect(lastFrame()).toContain('行0');
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
    await waitFor(() => hasTaskSocket());
    const socket = taskSocket();
    emit(socket, { event: 'task_end', status: 'succeeded', result: 'DONE: 这是模型的最终回答' });
    await waitFor(() => (lastFrame() ?? '').includes('这是模型的最终回答'));
    expect(lastFrame()).toContain('这是模型的最终回答');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app hides bare DONE sentinel from task_end result', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => hasTaskSocket());
    const socket = taskSocket();
    emit(socket, { event: 'task_end', status: 'succeeded', result: 'DONE' });
    await waitFor(() => (lastFrame() ?? '').includes('任务完成: succeeded'));
    expect(lastFrame()).not.toContain('[Agent]: DONE');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('tool call line shows failure marker for non-zero exit code', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => hasTaskSocket());
    const socket = taskSocket();
    // run_command 非零退出码（工具返回 ok=true 但 exit 1）→ 工具行应显示 ✗
    emit(socket, {
      event: 'tool_result',
      payload: {
        tool: 'run_command',
        ok: true,
        error: null,
        args: { command: 'python -m pytest' },
        output: '{"exit_code":1,"stdout":"","stderr":"FAILED test_foo.py::test_bar"}',
      },
    });
    await waitFor(() => (lastFrame() ?? '').includes('✗ exit 1'));
    expect(lastFrame()).toContain('✗ error: exit 1 · FAILED test_foo.py::test_bar');
    expect(lastFrame()).toContain('[Tool]: run_command("python -m pytest")');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app renders task_manage output as checklist', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => hasTaskSocket());
    const socket = taskSocket();
    emit(socket, {
      event: 'tool_result',
      payload: {
        tool: 'task_manage',
        ok: true,
        error: null,
        args: { action: 'list' },
        output:
          '[{"title":"读取文件","status":"pending"},{"title":"写入文件","status":"done"}]',
      },
    });
    await waitFor(() => (lastFrame() ?? '').includes('[ ] 读取文件'));
    expect(lastFrame()).toContain('[✓] 写入文件');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app toggles mouse tracking via /mouse (off by default for copy)', async () => {
  const fetchMock = urlFetchMock();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    // 默认关（随时鼠标选择复制）；/mouse 开启滚轮滚动
    stdin.write('/mouse');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('鼠标追踪: 开'));
    expect(lastFrame()).toContain('鼠标追踪: 开（滚轮滚动可用');
    // 再关：回到选择复制
    stdin.write('/mouse');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('鼠标追踪: 关'));
    expect(lastFrame()).toContain('鼠标追踪: 关（鼠标选择复制随时可用');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app shows plain replies by default and raw rounds in debug mode', async () => {
  const fetchMock = taskFetchMocks();
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('hello');
    stdin.write('\r');
    await waitFor(() => hasTaskSocket());
    const socket = taskSocket();
    // 默认模式：agent_message 显示纯文本；JSON 动作不进消息区（由工具行表达）
    emit(socket, { event: 'llm_call', payload: { iteration: 0 } });
    emit(socket, {
      event: 'llm_result',
      payload: { text: '我先看一下目录结构\n{"tool":"read_file","args":{}}' },
    });
    emit(socket, { event: 'agent_message', payload: { text: '我先看一下目录结构' } });
    await waitFor(() => (lastFrame() ?? '').includes('我先看一下目录结构'));
    expect(lastFrame()).not.toContain('[Agent 第1轮]');
    expect(lastFrame()).not.toContain('{"tool"');
    // 打开调试模式（/debug 与回车分开写，避免一次写入 \r 处理异常）
    stdin.write('/debug');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('调试模式: 开'));
    // debug 模式：llm_result 带轮次标签显示完整原始回复（含 JSON）
    emit(socket, { event: 'llm_call', payload: { iteration: 1 } });
    emit(socket, {
      event: 'llm_result',
      payload: { text: '第二次检查\n{"tool":"read_file","args":{"path":"a.ts"}}' },
    });
    await waitFor(() => (lastFrame() ?? '').includes('[Agent 第2轮]'));
    expect(lastFrame()).toContain('[Agent 第2轮] 第二次检查');
    stdin.write('\u001b[A');
    await sleep(100);
    expect(lastFrame()).toContain('"args":{"path":"a.ts"}');
    // DONE 回复不重复显示（由 task_end 显示最终回答）；失败显示具体原因
    emit(socket, { event: 'llm_result', payload: { text: 'DONE: 完成' } });
    emit(socket, { event: 'task_end', status: 'failed', result: 'MAX_ITERATIONS' });
    await waitFor(() => (lastFrame() ?? '').includes('任务失败: MAX_ITERATIONS'));
    expect(lastFrame()).toContain('任务失败: MAX_ITERATIONS');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('session manager only shows sessions from current workspace', async () => {
  let listCount = 0;
  const otherWorkspace =
    process.platform === 'win32' ? 'C:\other\project' : '/tmp/other-project';
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    if (url.includes('/api/v1/sessions') && method === 'GET') {
      listCount += 1;
      return {
        ok: true,
        status: 200,
        json: async () =>
          listCount === 1
            ? []
            : [
                { id: 's-local', workspace: process.cwd(), name: 'local', status: 'active' },
                { id: 's-other', workspace: otherWorkspace, name: 'other', status: 'active' },
              ],
      };
    }
    if (url.includes('/api/v1/sessions') && method === 'POST') return sessionResponse;
    if (url.includes('/config/model')) return modelConfigResponse;
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/session');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('会话管理'));
    await waitFor(() => (lastFrame() ?? '').includes('s-local'));
    expect(lastFrame()).toContain('s-local');
    expect(lastFrame()).not.toContain('s-other');
    expect(lastFrame()).not.toContain('other');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

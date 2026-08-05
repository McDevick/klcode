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

function taskFetchMocks() {
  return vi
    .fn()
    .mockResolvedValueOnce(sessionResponse)
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ id: 't1', session_id: 's1', description: 'hello', status: 'pending' }),
    })
    .mockResolvedValueOnce({ ok: true, status: 202, json: async () => ({ status: 'running' }) });
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
    tokensUsed: 240,
    maxTokens: 8000,
    toolCalls: [{ name: 'read_file', args: '{"path":"a.ts"}', summary: 'ok' }],
  };
  const { lastFrame, unmount } = render(<StatusCard running={running} />);
  try {
    expect(lastFrame()).toContain('正在执行推理');
    expect(lastFrame()).toContain('240/8000');
    expect(lastFrame()).toContain('read_file');
    expect(lastFrame()).toContain('ok');
  } finally {
    unmount();
  }
});

test('app creates a session and renders ready message', async () => {
  const fetchMock = vi.fn().mockResolvedValue(sessionResponse);
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    expect(lastFrame()).toContain('会话 s1 已就绪');
    expect(lastFrame()).toContain('klcode');
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
      2,
      'http://127.0.0.1:8700/api/v1/tasks',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
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
  const fetchMock = vi.fn().mockResolvedValue(sessionResponse);
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/');
    // 浮层菜单出现（测试视口较矮，断言窗口内靠底的可见项）
    await waitFor(() => (lastFrame() ?? '').includes('打开配置向导'));
    expect(lastFrame()).toContain('打开配置向导');

    // 滚动窗口：ArrowDown 一路到 /exit（index 8）后菜单滚动显示底部命令
    for (let i = 0; i < 8; i += 1) {
      stdin.write('[B');
    }
    await sleep(30);
    expect(lastFrame()).toContain('退出 TUI');

    // ArrowDown 回到 index 1（/session），Enter 填入输入框
    for (let i = 0; i < 7; i += 1) {
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
  const fetchMock = vi.fn().mockResolvedValue(sessionResponse);
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
  fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ status: 'canceled' }) });
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
    await waitFor(() => fetchMock.mock.calls.length >= 5);
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
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
  const fetchMock = vi.fn().mockResolvedValue(sessionResponse);
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
  const fetchMock = vi.fn().mockResolvedValue(sessionResponse);
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
  const fetchMock = vi.fn().mockResolvedValue(sessionResponse);
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

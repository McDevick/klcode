import { expect, test, vi } from 'vitest';
import { render } from 'ink-testing-library';
import React from 'react';
import { TaskInput } from '../src/tui/screens/task';
import { ApprovalPanel } from '../src/tui/screens/approval';
import { App } from '../src/tui/app';
import { ConfigWizard } from '../src/tui/screens/config';

test('task input renders prompt', () => {
  const { lastFrame } = render(<TaskInput onSubmit={() => {}} />);
  expect(lastFrame()).toContain('task>');
});

test('approval panel shows pending action', () => {
  const { lastFrame } = render(<ApprovalPanel tool="run_command" command="rm -rf /" />);
  expect(lastFrame()).toContain('requires approval');
  expect(lastFrame()).toContain('rm -rf /');
  expect(lastFrame()).toContain('[a]pprove [r]eject [m]odify');
});

test('task input submits value on enter', async () => {
  const onSubmit = vi.fn();
  const { stdin, unmount } = render(<TaskInput onSubmit={onSubmit} />);
  stdin.write('hello');
  stdin.write('\r');
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(onSubmit).toHaveBeenCalledWith('hello');
  unmount();
});

test('approval panel handles approve/reject/modify keys', () => {
  const onApprove = vi.fn();
  const onReject = vi.fn();
  const onModify = vi.fn();
  const { stdin, unmount } = render(
    <ApprovalPanel
      active
      tool="run_command"
      command="rm -rf /"
      onApprove={onApprove}
      onReject={onReject}
      onModify={onModify}
    />,
  );
  stdin.write('a');
  stdin.write('r');
  stdin.write('m');
  expect(onApprove).toHaveBeenCalled();
  expect(onReject).toHaveBeenCalled();
  expect(onModify).toHaveBeenCalled();
  unmount();
});

test('app submits task and shows approval actions', async () => {
  const { stdin, lastFrame, unmount } = render(<App />);
  stdin.write('hello');
  stdin.write('\r');
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(lastFrame()).toContain('task: hello');
  expect(lastFrame()).toContain('requires approval');
  stdin.write('a');
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(lastFrame()).toContain('approved');
  unmount();
});

test('config wizard accepts fields and saves hidden key', async () => {
  const onSave = vi.fn();
  const { stdin, lastFrame, unmount } = render(<ConfigWizard onSave={onSave} />);
  stdin.write('acme');
  stdin.write('\t');
  stdin.write('custom');
  stdin.write('\t');
  stdin.write('http://example.com');
  stdin.write('\t');
  stdin.write('model-x');
  stdin.write('\t');
  stdin.write('secret');
  stdin.write('\r');
  await new Promise((resolve) => setTimeout(resolve, 30));
  expect(lastFrame()).toContain('acme');
  expect(lastFrame()).toContain('http://example.com');
  expect(lastFrame()).toContain('model-x');
  expect(lastFrame()).toContain('******');
  expect(onSave).toHaveBeenCalledWith({
    providerName: 'acme',
    type: 'custom',
    baseUrl: 'http://example.com',
    model: 'model-x',
    apiKey: 'secret',
  });
  unmount();
});

test('app opens config wizard from /config', async () => {
  const { stdin, lastFrame, unmount } = render(<App />);
  stdin.write('/config');
  stdin.write('\r');
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(lastFrame()).toContain('config wizard');
  expect(lastFrame()).toContain('api key');
  stdin.write('acme');
  stdin.write('\t');
  stdin.write('custom');
  stdin.write('\t');
  stdin.write('http://example.com');
  stdin.write('\t');
  stdin.write('model-x');
  stdin.write('\t');
  stdin.write('secret');
  stdin.write('\r');
  await new Promise((resolve) => setTimeout(resolve, 30));
  expect(lastFrame()).toContain('config wizard');
  expect(lastFrame()).not.toContain('requires approval');
  unmount();
});

test('app runs session command from slash input', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ id: 's1' }],
    }),
  );
  const { stdin, lastFrame, unmount } = render(<App />);
  stdin.write('/sessions');
  stdin.write('\r');
  await new Promise((resolve) => setTimeout(resolve, 30));
  expect(lastFrame()).toContain('"id":"s1"');
  vi.unstubAllGlobals();
  unmount();
});

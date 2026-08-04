import { expect, test, vi } from 'vitest';
import { render } from 'ink-testing-library';
import React from 'react';
import { TaskInput } from '../src/tui/screens/task';
import { ApprovalPanel } from '../src/tui/screens/approval';
import { App } from '../src/tui/app';

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

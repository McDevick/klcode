import { expect, test } from 'vitest';
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

test('app renders event log', () => {
  const { lastFrame } = render(<App events={['tool_result ok', 'loop_end done']} />);
  expect(lastFrame()).toContain('tool_result ok');
  expect(lastFrame()).toContain('loop_end done');
});

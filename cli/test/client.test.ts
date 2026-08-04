import { expect, test } from 'vitest';
import { ApiClient } from '../src/api/client';

test('client builds task URL', () => {
  const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700' });
  expect(client.taskUrl('t1')).toBe('http://127.0.0.1:8700/api/v1/tasks/t1');
});

test('client trims trailing slash and encodes task id', () => {
  const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700/' });
  expect(client.taskUrl('a/b?c')).toBe('http://127.0.0.1:8700/api/v1/tasks/a%2Fb%3Fc');
});

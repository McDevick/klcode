import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

export function readDaemonToken(
  tokenPath: string = join(homedir(), '.kl', 'daemon.token'),
): string | undefined {
  try {
    const token = readFileSync(tokenPath, 'utf8').trim();
    return token.length > 0 ? token : undefined;
  } catch {
    return undefined;
  }
}

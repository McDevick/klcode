import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const pyprojectPath = join(root, '..', 'server', 'pyproject.toml');
const targetPath = join(root, 'src', 'server-version.ts');
const pyproject = readFileSync(pyprojectPath, 'utf8');
const match = pyproject.match(/^version\s*=\s*["']([^"']+)["']/m);
if (!match) {
  console.error('server/pyproject.toml missing version');
  process.exit(1);
}
const version = match[1];
const content = `export const SERVER_VERSION = '${version}';\n`;
if (process.argv.includes('--check')) {
  if (!existsSync(targetPath) || readFileSync(targetPath, 'utf8') !== content) {
    console.error(`server-version mismatch: expected ${version}`);
    process.exit(1);
  }
  console.log(`server-version ok: ${version}`);
  process.exit(0);
}
writeFileSync(targetPath, content, 'utf8');
console.log(`server-version synced: ${version}`);

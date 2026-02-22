import path from 'path';
import fs from 'fs';

const VAULT_ROOT = process.env.VAULT_PATH || path.resolve(__dirname, '..', '..', '..', '..', 'vault');

export function vaultRoot(): string {
  return VAULT_ROOT;
}

export function currentPatchVersion(): string {
  const pointerFile = path.join(VAULT_ROOT, 'patches', 'current', 'version.txt');
  if (!fs.existsSync(pointerFile)) throw new Error('No current patch version set. Run: pnpm ingest');
  return fs.readFileSync(pointerFile, 'utf-8').trim();
}

export function patchDir(version: string): string {
  return path.join(VAULT_ROOT, 'patches', version);
}

export function currentPatchDir(): string {
  return patchDir(currentPatchVersion());
}

export function trimmedPath(version: string): string {
  return path.join(patchDir(version), 'trimmed');
}

export function rawPath(version: string): string {
  return path.join(patchDir(version), 'raw');
}

export function canonPath(version: string): string {
  return path.join(patchDir(version), 'canon');
}

export function ensureDir(dir: string): void {
  fs.mkdirSync(dir, { recursive: true });
}

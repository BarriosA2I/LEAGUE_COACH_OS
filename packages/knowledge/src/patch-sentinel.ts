import axios from 'axios';
import fs from 'fs';
import path from 'path';
import { logger, vaultRoot, ensureDir } from '@league-coach/core';

const TAG = 'knowledge:patch-sentinel';
const VERSIONS_URL = 'https://ddragon.leagueoflegends.com/api/versions.json';
const TIMEOUT_MS = 15_000;

/**
 * Reads the current patch version from vault/patches/current/version.txt.
 * Returns null if the file does not exist (no patch has been set yet).
 */
function readCurrentVersion(): string | null {
  const pointerFile = path.join(vaultRoot(), 'patches', 'current', 'version.txt');
  if (!fs.existsSync(pointerFile)) return null;
  return fs.readFileSync(pointerFile, 'utf-8').trim();
}

/**
 * Fetches the latest patch version from DDragon's versions.json and
 * compares it against the currently stored version in the vault.
 *
 * @returns An object indicating whether the patch has changed, the
 *          current stored version (or null if none), and the latest
 *          version from DDragon.
 */
export async function detectNewPatch(): Promise<{
  changed: boolean;
  current: string | null;
  latest: string;
}> {
  logger.info(TAG, 'Checking for new patch version');

  const response = await axios.get<string[]>(VERSIONS_URL, { timeout: TIMEOUT_MS });
  const versions = response.data;

  if (!Array.isArray(versions) || versions.length === 0) {
    throw new Error('DDragon versions.json returned empty or invalid data');
  }

  // The first entry in versions.json is always the latest patch
  const latest = versions[0];
  const current = readCurrentVersion();
  const changed = current !== latest;

  logger.info(TAG, `Patch check`, { current, latest, changed });

  return { changed, current, latest };
}

/**
 * Writes the given version string to vault/patches/current/version.txt,
 * making it the active patch for all downstream consumers.
 */
export async function setCurrentPatch(version: string): Promise<void> {
  const dir = path.join(vaultRoot(), 'patches', 'current');
  ensureDir(dir);

  const pointerFile = path.join(dir, 'version.txt');
  fs.writeFileSync(pointerFile, version, 'utf-8');

  logger.info(TAG, `Current patch set to ${version}`);
}

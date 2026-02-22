import axios from 'axios';
import fs from 'fs';
import path from 'path';
import { logger, rawPath, ensureDir } from '@league-coach/core';

const TAG = 'knowledge:ingest';
const DDRAGON_BASE = 'https://ddragon.leagueoflegends.com/cdn';
const TIMEOUT_MS = 30_000;

const DATA_FILES = ['champion.json', 'item.json', 'runesReforged.json'] as const;

/**
 * Fetches champion.json, item.json, and runesReforged.json from the
 * Data Dragon CDN for a given patch version and writes the raw JSON
 * files into vault/patches/<version>/raw/.
 */
export async function ingestPatch(version: string): Promise<{
  version: string;
  championCount: number;
  itemCount: number;
  runeTreeCount: number;
}> {
  logger.info(TAG, `Ingesting patch ${version}`);

  const outDir = rawPath(version);
  ensureDir(outDir);

  const results: Record<string, unknown> = {};

  for (const file of DATA_FILES) {
    const url = `${DDRAGON_BASE}/${version}/data/en_US/${file}`;
    logger.info(TAG, `Fetching ${url}`);

    const response = await axios.get(url, { timeout: TIMEOUT_MS });
    const data = response.data;

    const outFile = path.join(outDir, file);
    fs.writeFileSync(outFile, JSON.stringify(data, null, 2), 'utf-8');
    logger.info(TAG, `Wrote ${outFile}`);

    results[file] = data;
  }

  const championData = results['champion.json'] as { data: Record<string, unknown> };
  const itemData = results['item.json'] as { data: Record<string, unknown> };
  const runeData = results['runesReforged.json'] as unknown[];

  const championCount = Object.keys(championData.data).length;
  const itemCount = Object.keys(itemData.data).length;
  const runeTreeCount = runeData.length;

  logger.info(TAG, `Ingest complete`, { version, championCount, itemCount, runeTreeCount });

  return { version, championCount, itemCount, runeTreeCount };
}

import fs from 'fs';
import path from 'path';
import {
  logger,
  rawPath,
  canonPath,
  trimmedPath,
  ensureDir,
  type TrimmedChampion,
  type TrimmedItem,
  type TrimmedRune,
  type RuneTree,
} from '@league-coach/core';

const TAG = 'knowledge:normalize';

// ---------------------------------------------------------------------------
// HTML stripping helper
// ---------------------------------------------------------------------------

/** Strips HTML tags from a string, returning plain text. */
function stripHtml(html: string): string {
  return html
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\s{2,}/g, ' ')
    .trim();
}

// ---------------------------------------------------------------------------
// Champion normalization
// ---------------------------------------------------------------------------

interface RawChampionEntry {
  id: string;
  name: string;
  title: string;
  tags: string[];
  partype: string;
  info: { attack: number; defense: number; magic: number; difficulty: number };
  stats: Record<string, number>;
  // Fields we discard: image, blurb, version, key, etc.
  [key: string]: unknown;
}

function normalizeChampions(raw: { data: Record<string, RawChampionEntry> }): {
  canon: Record<string, RawChampionEntry>;
  trimmed: TrimmedChampion[];
} {
  const canon: Record<string, RawChampionEntry> = raw.data;
  const trimmed: TrimmedChampion[] = [];

  for (const [, champ] of Object.entries(raw.data)) {
    trimmed.push({
      id: champ.id,
      name: champ.name,
      title: champ.title,
      tags: champ.tags,
      partype: champ.partype,
      info: champ.info,
      stats: champ.stats,
    });
  }

  return { canon, trimmed };
}

// ---------------------------------------------------------------------------
// Item normalization
// ---------------------------------------------------------------------------

interface RawItemEntry {
  name: string;
  gold: { total: number; sell: number; purchasable: boolean; base: number };
  stats: Record<string, number>;
  tags: string[];
  from?: string[];
  into?: string[];
  description: string;
  plaintext?: string;
  maps?: Record<string, boolean>;
  [key: string]: unknown;
}

function normalizeItems(raw: { data: Record<string, RawItemEntry> }): {
  canon: Record<string, RawItemEntry>;
  trimmed: TrimmedItem[];
} {
  const canon: Record<string, RawItemEntry> = raw.data;
  const trimmed: TrimmedItem[] = [];

  for (const [itemId, item] of Object.entries(raw.data)) {
    // Skip non-purchasable items
    if (!item.gold?.purchasable) continue;

    // Skip items not available on Summoner's Rift (map 11)
    if (item.maps && item.maps['11'] === false) continue;

    const description = item.plaintext || stripHtml(item.description || '');

    trimmed.push({
      id: itemId,
      name: item.name,
      cost: {
        total: item.gold.total,
        sell: item.gold.sell,
      },
      stats: item.stats || {},
      tags: item.tags || [],
      from: item.from || [],
      into: item.into || [],
      description,
    });
  }

  return { canon, trimmed };
}

// ---------------------------------------------------------------------------
// Rune normalization
// ---------------------------------------------------------------------------

interface RawRuneSlotEntry {
  id: number;
  key: string;
  name: string;
  shortDesc: string;
  longDesc: string;
  icon: string;
  [key: string]: unknown;
}

interface RawRuneTree {
  id: number;
  key: string;
  name: string;
  icon: string;
  slots: Array<{ runes: RawRuneSlotEntry[] }>;
  [key: string]: unknown;
}

function normalizeRunes(raw: RawRuneTree[]): {
  canon: RawRuneTree[];
  trimmed: RuneTree[];
} {
  const canon = raw;
  const trimmed: RuneTree[] = raw.map((tree) => ({
    id: tree.id,
    key: tree.key,
    name: tree.name,
    slots: tree.slots.map((slot) =>
      slot.runes.map(
        (rune): TrimmedRune => ({
          id: rune.id,
          key: rune.key,
          name: rune.name,
          shortDesc: stripHtml(rune.shortDesc),
          longDesc: stripHtml(rune.longDesc),
          icon: rune.icon,
        }),
      ),
    ),
  }));

  return { canon, trimmed };
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

/**
 * Reads raw DDragon data for a patch version and produces:
 *   - canon/  (full normalized JSON)
 *   - trimmed/ (lightweight JSON for agent consumption)
 */
export async function normalizePatch(version: string): Promise<void> {
  logger.info(TAG, `Normalizing patch ${version}`);

  const rawDir = rawPath(version);
  const canonDir = canonPath(version);
  const trimDir = trimmedPath(version);

  ensureDir(canonDir);
  ensureDir(trimDir);

  // --- Champions ---
  const champRaw = JSON.parse(fs.readFileSync(path.join(rawDir, 'champion.json'), 'utf-8'));
  const champs = normalizeChampions(champRaw);
  fs.writeFileSync(path.join(canonDir, 'champion-canon.json'), JSON.stringify(champs.canon, null, 2));
  fs.writeFileSync(path.join(trimDir, 'champion-trimmed.json'), JSON.stringify(champs.trimmed, null, 2));
  logger.info(TAG, `Champions: ${champs.trimmed.length} trimmed`);

  // --- Items ---
  const itemRaw = JSON.parse(fs.readFileSync(path.join(rawDir, 'item.json'), 'utf-8'));
  const items = normalizeItems(itemRaw);
  fs.writeFileSync(path.join(canonDir, 'item-canon.json'), JSON.stringify(items.canon, null, 2));
  fs.writeFileSync(path.join(trimDir, 'item-trimmed.json'), JSON.stringify(items.trimmed, null, 2));
  logger.info(TAG, `Items: ${items.trimmed.length} trimmed (from ${Object.keys(items.canon).length} total)`);

  // --- Runes ---
  const runeRaw = JSON.parse(fs.readFileSync(path.join(rawDir, 'runesReforged.json'), 'utf-8'));
  const runes = normalizeRunes(runeRaw);
  fs.writeFileSync(path.join(canonDir, 'rune-canon.json'), JSON.stringify(runes.canon, null, 2));
  fs.writeFileSync(path.join(trimDir, 'rune-trimmed.json'), JSON.stringify(runes.trimmed, null, 2));
  logger.info(TAG, `Rune trees: ${runes.trimmed.length} trimmed`);

  logger.info(TAG, `Normalization complete for ${version}`);
}

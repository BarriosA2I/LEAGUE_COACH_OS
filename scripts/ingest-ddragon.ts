import axios from 'axios';
import fs from 'fs';
import path from 'path';

const DDRAGON = 'https://ddragon.leagueoflegends.com';
const VAULT = path.resolve(__dirname, '..', 'vault');

function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/\s+/g, ' ').trim();
}

async function main() {
  // 1. Get latest version
  const { data: versions } = await axios.get<string[]>(`${DDRAGON}/api/versions.json`);
  const version = versions[0];
  console.log(`[Ingest] Latest patch: ${version}`);

  const rawDir = path.join(VAULT, 'patches', version, 'raw');
  const canonDir = path.join(VAULT, 'patches', version, 'canon');
  const trimmedDir = path.join(VAULT, 'patches', version, 'trimmed');
  const docsDir = path.join(VAULT, 'patches', version, 'docs');
  const currentDir = path.join(VAULT, 'patches', 'current');
  [rawDir, canonDir, trimmedDir, docsDir, currentDir].forEach(d => fs.mkdirSync(d, { recursive: true }));

  // 2. Fetch raw data
  const endpoints = ['champion.json', 'item.json', 'runesReforged.json'];
  for (const ep of endpoints) {
    console.log(`[Ingest] Fetching ${ep}...`);
    const { data } = await axios.get(`${DDRAGON}/cdn/${version}/data/en_US/${ep}`);
    fs.writeFileSync(path.join(rawDir, ep), JSON.stringify(data, null, 2));
  }

  // 3. Normalize champions
  const champRaw = JSON.parse(fs.readFileSync(path.join(rawDir, 'champion.json'), 'utf-8'));
  const champions = Object.values(champRaw.data).map((c: any) => ({
    id: c.id, name: c.name, title: c.title, tags: c.tags, partype: c.partype,
    info: c.info, stats: c.stats,
  }));
  champions.sort((a: any, b: any) => a.name.localeCompare(b.name));
  fs.writeFileSync(path.join(canonDir, 'champions.json'), JSON.stringify(champRaw.data, null, 2));
  fs.writeFileSync(path.join(trimmedDir, 'champion-trimmed.json'), JSON.stringify(champions, null, 2));
  console.log(`[Ingest] ${champions.length} champions trimmed`);

  // 4. Normalize items
  const itemRaw = JSON.parse(fs.readFileSync(path.join(rawDir, 'item.json'), 'utf-8'));
  const items = Object.entries(itemRaw.data)
    .filter(([, v]: any) => v.gold.purchasable && (!v.maps || v.maps['11'] !== false))
    .map(([id, v]: any) => ({
      id, name: v.name, cost: { total: v.gold.total, sell: v.gold.sell },
      stats: v.stats, tags: v.tags, from: v.from || [], into: v.into || [],
      description: v.plaintext || stripHtml(v.description),
    }));
  items.sort((a: any, b: any) => a.name.localeCompare(b.name));
  fs.writeFileSync(path.join(canonDir, 'items.json'), JSON.stringify(itemRaw.data, null, 2));
  fs.writeFileSync(path.join(trimmedDir, 'item-trimmed.json'), JSON.stringify(items, null, 2));
  console.log(`[Ingest] ${items.length} items trimmed`);

  // 5. Normalize runes
  const runeRaw = JSON.parse(fs.readFileSync(path.join(rawDir, 'runesReforged.json'), 'utf-8'));
  const runes = runeRaw.map((tree: any) => ({
    id: tree.id, key: tree.key, name: tree.name, icon: tree.icon,
    slots: tree.slots.map((slot: any) => slot.runes.map((r: any) => ({
      id: r.id, key: r.key, name: r.name, shortDesc: stripHtml(r.shortDesc),
      longDesc: stripHtml(r.longDesc), icon: r.icon,
    }))),
  }));
  fs.writeFileSync(path.join(canonDir, 'runes.json'), JSON.stringify(runeRaw, null, 2));
  fs.writeFileSync(path.join(trimmedDir, 'rune-trimmed.json'), JSON.stringify(runes, null, 2));
  console.log(`[Ingest] ${runes.length} rune trees trimmed`);

  // 6. Write manifest
  const manifest = {
    version,
    fetched_at: new Date().toISOString(),
    champion_count: champions.length,
    item_count: items.length,
    rune_tree_count: runes.length,
  };
  fs.writeFileSync(path.join(trimmedDir, 'manifest.json'), JSON.stringify(manifest, null, 2));

  // 7. Set current pointer
  fs.writeFileSync(path.join(currentDir, 'version.txt'), version);
  console.log(`[Ingest] Current patch set to ${version}`);
  console.log('[Ingest] Done.');
}

main().catch(err => { console.error('[Ingest] Fatal:', err.message); process.exit(1); });

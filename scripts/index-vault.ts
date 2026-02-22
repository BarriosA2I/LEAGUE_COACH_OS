import fs from 'fs';
import path from 'path';

const VAULT = path.resolve(__dirname, '..', 'vault');

function getCurrentVersion(): string {
  return fs.readFileSync(path.join(VAULT, 'patches', 'current', 'version.txt'), 'utf-8').trim();
}

interface IndexEntry {
  type: 'champion' | 'item' | 'rune_tree';
  id: string;
  name: string;
  tags: string[];
  patch: string;
}

async function main() {
  const version = getCurrentVersion();
  const trimmedDir = path.join(VAULT, 'patches', version, 'trimmed');
  const index: IndexEntry[] = [];

  const champions = JSON.parse(fs.readFileSync(path.join(trimmedDir, 'champion-trimmed.json'), 'utf-8'));
  for (const c of champions) {
    index.push({ type: 'champion', id: c.id, name: c.name, tags: c.tags, patch: version });
  }

  const items = JSON.parse(fs.readFileSync(path.join(trimmedDir, 'item-trimmed.json'), 'utf-8'));
  for (const i of items) {
    index.push({ type: 'item', id: i.id, name: i.name, tags: i.tags, patch: version });
  }

  const runes = JSON.parse(fs.readFileSync(path.join(trimmedDir, 'rune-trimmed.json'), 'utf-8'));
  for (const tree of runes) {
    index.push({ type: 'rune_tree', id: String(tree.id), name: tree.name, tags: [tree.key], patch: version });
  }

  const indexPath = path.join(VAULT, 'meta', 'search-index.json');
  fs.writeFileSync(indexPath, JSON.stringify(index, null, 2));
  console.log(`[Index] Built search index: ${index.length} entries for patch ${version}`);

  // Also build a name lookup map
  const lookup: Record<string, string> = {};
  for (const c of champions) {
    lookup[c.name.toLowerCase()] = c.id;
    lookup[c.id.toLowerCase()] = c.id;
  }
  fs.writeFileSync(path.join(VAULT, 'meta', 'champion-lookup.json'), JSON.stringify(lookup, null, 2));
  console.log(`[Index] Built champion lookup: ${Object.keys(lookup).length} entries`);
}

main().catch(err => { console.error('[Index] Fatal:', err.message); process.exit(1); });

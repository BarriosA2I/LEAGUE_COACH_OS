import axios from 'axios';
import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';

const VAULT = path.resolve(__dirname, '..', 'vault');
const VERSIONS_URL = 'https://ddragon.leagueoflegends.com/api/versions.json';

async function main() {
  const { data: versions } = await axios.get<string[]>(VERSIONS_URL);
  const latest = versions[0];

  const pointerFile = path.join(VAULT, 'patches', 'current', 'version.txt');
  const current = fs.existsSync(pointerFile) ? fs.readFileSync(pointerFile, 'utf-8').trim() : null;

  if (current === latest) {
    console.log(`[Sentinel] No change. Current: ${current}`);
    return;
  }

  console.log(`[Sentinel] New patch detected: ${current || '(none)'} -> ${latest}`);
  console.log('[Sentinel] Running ingest...');
  execSync('tsx scripts/ingest-ddragon.ts', { stdio: 'inherit', cwd: path.resolve(__dirname, '..') });
  console.log('[Sentinel] Ingest complete.');
}

main().catch(err => { console.error('[Sentinel] Fatal:', err.message); process.exit(1); });

import fs from 'fs';
import path from 'path';

const VAULT = path.resolve(__dirname, '..', 'vault');

function getCurrentVersion(): string {
  return fs.readFileSync(path.join(VAULT, 'patches', 'current', 'version.txt'), 'utf-8').trim();
}

const ROLE_MAP: Record<string, string> = {
  Fighter: 'Top / Jungle', Tank: 'Top / Support', Mage: 'Mid',
  Assassin: 'Mid / Jungle', Marksman: 'ADC', Support: 'Support',
};

async function main() {
  const version = getCurrentVersion();
  const trimmedDir = path.join(VAULT, 'patches', version, 'trimmed');
  const champions = JSON.parse(fs.readFileSync(path.join(trimmedDir, 'champion-trimmed.json'), 'utf-8'));

  const dossierDir = path.join(VAULT, 'champions', 'dossiers', version);
  fs.mkdirSync(dossierDir, { recursive: true });

  for (const champ of champions) {
    const roles = champ.tags.map((t: string) => ROLE_MAP[t] || t).join(', ');
    const md = [
      `# ${champ.name}`,
      `> ${champ.title}`,
      '',
      `**Roles:** ${roles}`,
      `**Resource:** ${champ.partype}`,
      `**Difficulty:** ${champ.info.difficulty}/10`,
      '',
      `## Base Stats`,
      `| Stat | Value | Per Level |`,
      `|------|-------|-----------|`,
      `| HP | ${champ.stats.hp} | +${champ.stats.hpperlevel} |`,
      `| AD | ${champ.stats.attackdamage} | +${champ.stats.attackdamageperlevel} |`,
      `| Armor | ${champ.stats.armor} | +${champ.stats.armorperlevel} |`,
      `| MR | ${champ.stats.spellblock} | +${champ.stats.spellblockperlevel} |`,
      `| Move Speed | ${champ.stats.movespeed} | - |`,
      `| Attack Range | ${champ.stats.attackrange} | - |`,
      '',
      `## Tags`,
      champ.tags.map((t: string) => `- ${t}`).join('\n'),
    ].join('\n');

    fs.writeFileSync(path.join(dossierDir, `${champ.id}.md`), md);
  }

  console.log(`[Dossiers] Generated ${champions.length} dossiers for patch ${version}`);
}

main().catch(err => { console.error('[Dossiers] Fatal:', err.message); process.exit(1); });

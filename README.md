# LEAGUE_COACH_OS

Multi-agent League of Legends coaching system by Barrios A2I.

Upload a loading screen (or manually input champions), and the system identifies all 10 champions, detects your circled champion, infers your role, and outputs a complete coaching package: builds, runes, skill order, and tips.

## Quick Start

```bash
# 1. Install dependencies
pnpm install

# 2. Populate the Knowledge Vault with current patch data
pnpm ingest

# 3. Generate champion dossiers and search index
pnpm dossiers
pnpm index-vault

# 4. Run the coach (FAST MODE with manual input)
pnpm coach -- --champions "blue:Teemo,blue:LeeSin,blue:Syndra,blue:Jinx,blue:Thresh,red:Darius,red:Elise,red:Ahri,red:Caitlyn,red:Lulu" --user Teemo
```

## Architecture

```
apps/          Web UI and API (future)
packages/
  core/        Shared Zod schemas, types, utilities
  orchestrator Agent runner and pipeline
  vision/      Image parsing + circled champion detection
  knowledge/   Data Dragon ingestion, patch sentinel
  agents/      Agent prompts, adapters, registry
  eval/        Judge, validators, test harness
vault/         Knowledge Vault (game data source of truth)
scripts/       CLI tools for vault management
docs/          Architecture documentation
fixtures/      Test images and expected outputs
```

## Key Commands

| Command | Description |
|---------|-------------|
| `pnpm ingest` | Download latest patch data into vault |
| `pnpm sentinel` | Check for new patches and auto-ingest |
| `pnpm dossiers` | Generate champion markdown profiles |
| `pnpm index-vault` | Build searchable index |
| `pnpm coach` | Run the coaching pipeline |
| `pnpm build` | Build all packages |
| `pnpm test` | Run all tests |

## Modes

**FAST MODE** (implemented): Uses vault data + tag-based defaults. Sub-second response.

**FULL MODE** (stubs): Adds matchup reasoning, team comp analysis, macro coaching, and patch delta adjustments.

## Docs

- [VAULT.md](docs/VAULT.md) How the Knowledge Vault works
- [AGENTS.md](docs/AGENTS.md) Agent registry and pipeline
- [WORKFLOWS.md](docs/WORKFLOWS.md) FAST and FULL mode workflows
- [SCHEMAS.md](docs/SCHEMAS.md) All Zod schemas

## Environment

Copy `.env.example` to `.env` and fill in API keys (only needed for FULL MODE with LLM agents).

## Tech Stack

TypeScript, Node 20+, pnpm workspaces, Zod, sharp, vitest

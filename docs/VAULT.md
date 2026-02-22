# Knowledge Vault

The vault is the single source of truth for all League of Legends game data. Every agent reads from the vault; no agent fetches data from the internet at runtime.

## Structure

```
vault/
  patches/
    current/version.txt          # plain text: "16.4.1"
    16.4.1/
      raw/                       # untouched JSON from Data Dragon
        champion.json
        item.json
        runesReforged.json
      canon/                     # normalized full data
        champions.json
        items.json
        runes.json
      trimmed/                   # agent-ready minimal data
        champion-trimmed.json
        item-trimmed.json
        rune-trimmed.json
        manifest.json
      docs/                      # patch notes, delta summaries
      embeddings/                # future: vector store exports
  champions/
    dossiers/<patch>/            # per-champion markdown profiles
    playbooks/<patch>/           # role-specific playbooks
    matchups/<patch>/            # matchup analysis docs
  roles/
    fundamentals/                # macro guides per role
  meta/
    priors/                      # role inference heuristics
    templates/                   # prompt templates, schemas
    search-index.json            # flat searchable index
    champion-lookup.json         # name -> id mapping
```

## How Agents Learn

1. **Patch Sentinel** (`pnpm sentinel`) polls Data Dragon for new versions
2. **Ingest** (`pnpm ingest`) downloads raw data, normalizes to canon, trims to agent format
3. **Current pointer** (`vault/patches/current/version.txt`) always points to the active patch
4. Agents call `currentPatchVersion()` from `@league-coach/core` to resolve the active patch
5. Agents read trimmed data from `vault/patches/<version>/trimmed/`
6. Agents never write to the vault. Only scripts do.

## Data Flow

```
Data Dragon API
      |
      v
  raw/ (exact API response)
      |
      v
  canon/ (normalized, full fidelity)
      |
      v
  trimmed/ (minimal, typed, agent-ready)
      |
      v
  Agents read trimmed data via @league-coach/core vault-path utilities
```

## Updating

When a new patch drops:
1. `pnpm sentinel` detects the version change
2. Automatically runs `pnpm ingest` which creates a new patch folder
3. Run `pnpm dossiers` to regenerate champion profiles
4. Run `pnpm index-vault` to rebuild the search index
5. The `current` pointer updates automatically

## Trimmed Data Schemas

All trimmed data conforms to Zod schemas defined in `packages/core/src/schemas/knowledge.ts`. Agents can trust the shape of this data without runtime validation.

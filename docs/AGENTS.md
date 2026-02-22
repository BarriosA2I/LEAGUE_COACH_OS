# Agent Registry

All agents are registered in `packages/agents/src/registry/agent-registry.ts`. Each agent has typed Zod input/output schemas and a deterministic `execute()` function.

## FAST MODE Agents (Implemented)

### vision_parser
Parses loading screen to identify 10 champions and the user's champion.
FAST MODE accepts manual champion input as a fallback when image recognition is unavailable.

### user_context_resolver
Takes vision output and extracts: user champion, team affiliation, allies list, enemies list.

### role_inference_engine
Infers the user's role (top/jungle/mid/adc/support) based on champion tags and team composition.
Uses `ROLE_TAG_MAP` from core for deterministic mapping.

### canon_knowledge_fetcher
Loads champion data, item catalog, and rune trees from the vault's trimmed data for the current patch.

### build_and_runes_planner
Generates recommended build (starter, core, boots, situational), rune page, skill order, and tips.
FAST MODE uses tag-based defaults (e.g., Fighter -> Conqueror + Trinity Force).

### final_judge_validator
Validates the assembled GAME_COACH_PACKAGE against the Zod schema. Rejects packages with missing or invalid fields.

## FULL MODE Agents (Stubs)

### laning_matchup_coach
Will analyze specific lane matchups using champion dossiers and matchup data.

### teamfight_comp_coach
Will evaluate team compositions and suggest teamfight strategies.

### macro_objectives_coach
Will provide objective-based macro coaching (dragon priority, split push, etc.).

## Pipeline Order

```
1. vision_parser
2. user_context_resolver
3. role_inference_engine
4. canon_knowledge_fetcher
5. build_and_runes_planner
6. final_judge_validator
```

## Adding a New Agent

1. Create `packages/agents/src/registry/<agent-name>.ts`
2. Define Zod input/output schemas
3. Implement `execute()` returning `AgentResult`
4. Register in `agent-registry.ts`
5. Wire into orchestrator pipeline if needed

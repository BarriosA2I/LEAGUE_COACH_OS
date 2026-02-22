# Schemas

All schemas are defined with Zod in `packages/core/src/schemas/`. Every agent input and output is validated at runtime.

## GAME_COACH_PACKAGE

The final output of the coaching pipeline.

```typescript
{
  patch: string;              // "16.4.1"
  timestamp: string;          // ISO 8601
  user_champion: string;      // "Aatrox"
  user_role: Role;            // "top" | "jungle" | "mid" | "adc" | "support"
  blue_team: string[5];
  red_team: string[5];
  recommended_build: {
    starter: string[];        // ["Doran's Blade", "Health Potion"]
    core_items: string[];     // 2-4 items
    boots: string;
    situational: string[];
  };
  recommended_runes: {
    primary_tree: string;     // "Precision"
    primary_keystone: string; // "Conqueror"
    primary_slots: string[3];
    secondary_tree: string;   // "Resolve"
    secondary_slots: string[2];
  };
  skill_order: {
    first_three: string[3];   // ["Q", "W", "E"]
    max_order: string[];      // ["Q", "W", "E"]
  };
  laning_tips: string[];
  teamfight_tips: string[];
  objective_tips: string[];
  confidence: number;         // 0.0 - 1.0
  warnings: string[];
}
```

## VisionParseOutput

```typescript
{
  blue_team: Array<{ champion: string; confidence: number }>[5];
  red_team: Array<{ champion: string; confidence: number }>[5];
  user_champion: string;
  user_confidence: number;
  unknown_slots: number[];
}
```

## AgentResult

```typescript
{
  agent: AgentName;
  success: boolean;
  data: unknown;
  errors?: string[];
  duration_ms: number;
}
```

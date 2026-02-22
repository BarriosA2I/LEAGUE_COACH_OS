# Workflows

## FAST MODE (MVP)

The default workflow. Produces a GAME_COACH_PACKAGE in under 1 second using only local vault data.

### Input
```json
{
  "image_path": "fixtures/images/loading-screen.png",
  "manual_champions": [
    "blue:Aatrox", "blue:LeeSin", "blue:Syndra", "blue:Jinx", "blue:Thresh",
    "red:Darius", "red:Elise", "red:Ahri", "red:Caitlyn", "red:Lulu",
    "user:Aatrox"
  ]
}
```

### Pipeline
1. Vision parser reads manual_champions, assigns teams
2. User context resolver identifies user as Aatrox on blue team
3. Role inference maps Aatrox (Fighter tag) to top lane
4. Knowledge fetcher loads Aatrox stats, full item catalog, rune trees
5. Build planner generates Fighter/Top defaults
6. Judge validates the complete package

### Output
A validated GAME_COACH_PACKAGE JSON (see SCHEMAS.md).

## FULL MODE (Future)

Extends FAST MODE with:
- Matchup-specific laning tips (laning_matchup_coach)
- Team comp analysis (teamfight_comp_coach)
- Macro objective priorities (macro_objectives_coach)
- Patch delta adjustments

## CLI Usage

```bash
# Run with manual champions
pnpm coach -- --champions "blue:Aatrox,blue:LeeSin,blue:Syndra,blue:Jinx,blue:Thresh,red:Darius,red:Elise,red:Ahri,red:Caitlyn,red:Lulu" --user Aatrox

# Run with image (future)
pnpm coach -- --image fixtures/images/loading-screen.png
```

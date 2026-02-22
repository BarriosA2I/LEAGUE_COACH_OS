import { describe, it, expect } from 'vitest';
import {
  GameCoachPackageSchema,
  VisionParseOutputSchema,
  type GameCoachPackage,
} from '@league-coach/core';
import { judgeOutput } from './judge';

// ---------------------------------------------------------------------------
// Fixture: a valid GAME_COACH_PACKAGE for Teemo top
// ---------------------------------------------------------------------------

const VALID_TEEMO_PACKAGE: GameCoachPackage = {
  patch: '16.4.1',
  timestamp: '2026-02-22T12:00:00.000Z',
  user_champion: 'Teemo',
  user_role: 'top',
  blue_team: ['Teemo', 'Amumu', 'Lux', 'Jinx', 'Thresh'],
  red_team: ['Darius', 'Lee Sin', 'Ahri', 'Caitlyn', 'Leona'],
  recommended_build: {
    starter: ["Doran's Blade", 'Health Potion'],
    core_items: ['Nashor\'s Tooth', 'Liandry\'s Anguish', 'Zhonya\'s Hourglass'],
    boots: "Sorcerer's Shoes",
    situational: ['Void Staff', 'Morellonomicon', "Banshee's Veil"],
  },
  recommended_runes: {
    primary_tree: 'Sorcery',
    primary_keystone: 'Arcane Comet',
    primary_slots: ['Manaflow Band', 'Transcendence', 'Scorch'],
    secondary_tree: 'Domination',
    secondary_slots: ['Taste of Blood', 'Treasure Hunter'],
  },
  skill_order: {
    first_three: ['Q', 'E', 'W'],
    max_order: ['E', 'Q', 'W'],
  },
  laning_tips: [
    'Poke with auto attacks and Toxic Shot (E) passive for free trades.',
    'Place Noxious Traps (R) in river bushes to track the enemy jungler.',
    'Blind (Q) the enemy laner when they try to last-hit cannon minions.',
  ],
  teamfight_tips: [
    'Stay at the edges of fights and kite with your movement speed from W.',
    'Use mushrooms to zone enemies away from objectives.',
  ],
  objective_tips: [
    'Shroom around dragon and baron pit 60s before spawn.',
    'Split push with mushroom coverage for safe escape routes.',
  ],
  confidence: 0.85,
  warnings: [],
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('GameCoachPackageSchema validation', () => {
  it('should accept a valid GAME_COACH_PACKAGE', () => {
    const result = GameCoachPackageSchema.safeParse(VALID_TEEMO_PACKAGE);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.user_champion).toBe('Teemo');
      expect(result.data.user_role).toBe('top');
      expect(result.data.patch).toBe('16.4.1');
    }
  });

  it('should reject a package with missing required fields', () => {
    const incomplete = {
      patch: '16.4.1',
      timestamp: '2026-02-22T12:00:00.000Z',
      user_champion: 'Teemo',
      // missing: user_role, blue_team, red_team, recommended_build, etc.
    };

    const result = GameCoachPackageSchema.safeParse(incomplete);
    expect(result.success).toBe(false);
    if (!result.success) {
      // Should have errors for all missing required fields
      const paths = result.error.issues.map((i) => i.path[0]);
      expect(paths).toContain('user_role');
      expect(paths).toContain('blue_team');
      expect(paths).toContain('red_team');
      expect(paths).toContain('recommended_build');
      expect(paths).toContain('recommended_runes');
    }
  });

  it('should reject an invalid role enum value', () => {
    const badRole = {
      ...VALID_TEEMO_PACKAGE,
      user_role: 'toplaner', // not in enum
    };

    const result = GameCoachPackageSchema.safeParse(badRole);
    expect(result.success).toBe(false);
    if (!result.success) {
      const roleIssue = result.error.issues.find((i) => i.path.includes('user_role'));
      expect(roleIssue).toBeDefined();
    }
  });

  it('should reject a package with wrong team size', () => {
    const wrongTeamSize = {
      ...VALID_TEEMO_PACKAGE,
      blue_team: ['Teemo', 'Amumu', 'Lux'], // only 3 instead of 5
    };

    const result = GameCoachPackageSchema.safeParse(wrongTeamSize);
    expect(result.success).toBe(false);
    if (!result.success) {
      const teamIssue = result.error.issues.find((i) =>
        i.path.includes('blue_team'),
      );
      expect(teamIssue).toBeDefined();
    }
  });
});

describe('VisionParseOutputSchema validation', () => {
  it('should reject vision output with wrong team size', () => {
    const badVision = {
      blue_team: [
        { champion: 'Teemo', confidence: 1.0 },
        { champion: 'Amumu', confidence: 1.0 },
        // only 2 slots instead of 5
      ],
      red_team: [
        { champion: 'Darius', confidence: 1.0 },
        { champion: 'Lee Sin', confidence: 1.0 },
        { champion: 'Ahri', confidence: 1.0 },
        { champion: 'Caitlyn', confidence: 1.0 },
        { champion: 'Leona', confidence: 1.0 },
      ],
      user_champion: 'Teemo',
      user_confidence: 1.0,
      unknown_slots: [],
    };

    const result = VisionParseOutputSchema.safeParse(badVision);
    expect(result.success).toBe(false);
    if (!result.success) {
      const teamIssue = result.error.issues.find((i) =>
        i.path.includes('blue_team'),
      );
      expect(teamIssue).toBeDefined();
    }
  });

  it('should accept a valid VisionParseOutput', () => {
    const validVision = {
      blue_team: [
        { champion: 'Teemo', confidence: 1.0 },
        { champion: 'Amumu', confidence: 1.0 },
        { champion: 'Lux', confidence: 1.0 },
        { champion: 'Jinx', confidence: 1.0 },
        { champion: 'Thresh', confidence: 1.0 },
      ],
      red_team: [
        { champion: 'Darius', confidence: 1.0 },
        { champion: 'Lee Sin', confidence: 1.0 },
        { champion: 'Ahri', confidence: 1.0 },
        { champion: 'Caitlyn', confidence: 1.0 },
        { champion: 'Leona', confidence: 1.0 },
      ],
      user_champion: 'Teemo',
      user_confidence: 1.0,
      unknown_slots: [],
    };

    const result = VisionParseOutputSchema.safeParse(validVision);
    expect(result.success).toBe(true);
  });
});

describe('judgeOutput', () => {
  it('should return valid=true for a correct package', () => {
    const result = judgeOutput(VALID_TEEMO_PACKAGE);
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
    expect(result.parsed).not.toBeNull();
    expect(result.parsed!.user_champion).toBe('Teemo');
  });

  it('should return valid=false with detailed errors for invalid input', () => {
    const result = judgeOutput({ patch: '16.4.1' });
    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.parsed).toBeNull();
    // Each error should include path and message
    for (const err of result.errors) {
      expect(err).toMatch(/\[.*\]/); // has path in brackets
    }
  });

  it('should reject confidence out of range', () => {
    const badConfidence = {
      ...VALID_TEEMO_PACKAGE,
      confidence: 1.5, // exceeds max of 1
    };
    const result = judgeOutput(badConfidence);
    expect(result.valid).toBe(false);
    const confErr = result.errors.find((e) => e.includes('confidence'));
    expect(confErr).toBeDefined();
  });
});

import { z } from 'zod';
import {
  type AgentDefinition,
  type AgentResult,
  type Role,
  type TrimmedChampion,
  type TrimmedItem,
  type RuneTree,
  TrimmedChampionSchema,
  TrimmedItemSchema,
  RuneTreeSchema,
  RecommendedBuildSchema,
  RecommendedRunesSchema,
  SkillOrderSchema,
  type RecommendedBuild,
  type RecommendedRunes,
  type SkillOrder,
} from '@league-coach/core';

// ---------------------------------------------------------------------------
// Input / Output schemas
// ---------------------------------------------------------------------------

const BuildPlannerInputSchema = z.object({
  champion: z.string(),
  role: z.enum(['top', 'jungle', 'mid', 'adc', 'support']),
  champion_data: TrimmedChampionSchema,
  items: z.array(TrimmedItemSchema),
  rune_trees: z.array(RuneTreeSchema),
});

type BuildPlannerInput = z.infer<typeof BuildPlannerInputSchema>;

const BuildPlannerOutputSchema = z.object({
  recommended_build: RecommendedBuildSchema,
  recommended_runes: RecommendedRunesSchema,
  skill_order: SkillOrderSchema,
  laning_tips: z.array(z.string()),
  teamfight_tips: z.array(z.string()),
  objective_tips: z.array(z.string()),
});

export type BuildPlannerOutput = z.infer<typeof BuildPlannerOutputSchema>;

// ---------------------------------------------------------------------------
// FAST MODE defaults -- hardcoded builds by champion tag + role
// ---------------------------------------------------------------------------

interface RoleBuildDefaults {
  starter: string[];
  core_items: string[];
  boots: string;
  situational: string[];
  primary_tree: string;
  primary_keystone: string;
  primary_slots: [string, string, string];
  secondary_tree: string;
  secondary_slots: [string, string];
  skill_first_three: [string, string, string];
  skill_max_order: string[];
  laning_tips: string[];
  teamfight_tips: string[];
  objective_tips: string[];
}

const ROLE_BUILD_DEFAULTS: Record<string, RoleBuildDefaults> = {
  'Fighter/top': {
    starter: ["Doran's Blade", 'Health Potion'],
    core_items: ['Trinity Force', "Sterak's Gage", "Death's Dance"],
    boots: 'Plated Steelcaps',
    situational: ["Guardian Angel", "Maw of Malmortius", "Hullbreaker"],
    primary_tree: 'Precision',
    primary_keystone: 'Conqueror',
    primary_slots: ['Triumph', 'Legend: Tenacity', 'Last Stand'],
    secondary_tree: 'Resolve',
    secondary_slots: ['Bone Plating', 'Unflinching'],
    skill_first_three: ['Q', 'W', 'E'],
    skill_max_order: ['Q', 'W', 'E'],
    laning_tips: [
      'Trade aggressively when Conqueror is fully stacked.',
      'Manage wave near your tower to set up ganks.',
      'Use your sustain advantage to outlast short trades.',
    ],
    teamfight_tips: [
      'Dive the backline or peel for your carry depending on team needs.',
      'Wait for key enemy cooldowns before fully engaging.',
    ],
    objective_tips: [
      'Split push when your teleport is available to create pressure.',
      'Contest Rift Herald for early tower plates.',
    ],
  },
  'Tank/top': {
    starter: ["Doran's Shield", 'Health Potion'],
    core_items: ['Sunfire Aegis', 'Thornmail', 'Spirit Visage'],
    boots: 'Plated Steelcaps',
    situational: ["Warmog's Armor", "Randuin's Omen", "Gargoyle Stoneplate"],
    primary_tree: 'Resolve',
    primary_keystone: 'Grasp of the Undying',
    primary_slots: ['Demolish', 'Conditioning', 'Overgrowth'],
    secondary_tree: 'Precision',
    secondary_slots: ['Triumph', 'Legend: Tenacity'],
    skill_first_three: ['Q', 'W', 'E'],
    skill_max_order: ['Q', 'W', 'E'],
    laning_tips: [
      'Stack Grasp procs for free HP and trade advantage.',
      'Use your tankiness to absorb enemy jungle pressure.',
      'Focus on farm and scaling -- you outscale most lane bullies.',
    ],
    teamfight_tips: [
      'Frontline for your team and soak damage.',
      'Use CC to lock down priority targets for your carries.',
    ],
    objective_tips: [
      'Use Demolish to take towers quickly after winning trades.',
      'Tank dragon/baron aggro for your team.',
    ],
  },
  'Tank/support': {
    starter: ['Relic Shield', 'Health Potion'],
    core_items: ['Locket of the Iron Solari', "Knight's Vow", "Zeke's Convergence"],
    boots: 'Plated Steelcaps',
    situational: ["Redemption", "Thornmail", "Gargoyle Stoneplate"],
    primary_tree: 'Resolve',
    primary_keystone: 'Guardian',
    primary_slots: ['Font of Life', 'Bone Plating', 'Unflinching'],
    secondary_tree: 'Inspiration',
    secondary_slots: ['Hextech Flashtraption', 'Cosmic Insight'],
    skill_first_three: ['Q', 'W', 'E'],
    skill_max_order: ['Q', 'W', 'E'],
    laning_tips: [
      'Stand in front of your ADC to zone and threaten engage.',
      'Proc Relic Shield charges on cannon minions for max gold.',
      'Roam after pushing the wave to impact mid lane.',
    ],
    teamfight_tips: [
      'Engage fights or peel for your carries based on the situation.',
      'Use Locket shield at the right moment to absorb burst.',
    ],
    objective_tips: [
      'Place deep wards around objectives 60 seconds before spawn.',
      'Use Oracle Lens to deny enemy vision around dragon/baron.',
    ],
  },
  'Mage/mid': {
    starter: ["Doran's Ring", 'Health Potion'],
    core_items: ["Luden's Tempest", "Zhonya's Hourglass", "Rabadon's Deathcap"],
    boots: "Sorcerer's Shoes",
    situational: ['Void Staff', "Banshee's Veil", 'Morellonomicon'],
    primary_tree: 'Sorcery',
    primary_keystone: 'Arcane Comet',
    primary_slots: ['Manaflow Band', 'Transcendence', 'Scorch'],
    secondary_tree: 'Inspiration',
    secondary_slots: ['Biscuit Delivery', 'Cosmic Insight'],
    skill_first_three: ['Q', 'W', 'E'],
    skill_max_order: ['Q', 'W', 'E'],
    laning_tips: [
      'Poke with abilities to proc Arcane Comet and Manaflow Band.',
      'Manage mana carefully -- use Biscuits to sustain through lane.',
      'Ward river at 3:15 to track the enemy jungler.',
    ],
    teamfight_tips: [
      'Stay at max range and focus on landing AoE abilities.',
      "Use Zhonya's to survive assassin dives or key enemy cooldowns.",
    ],
    objective_tips: [
      'Use waveclear to maintain priority before objectives.',
      'Zone enemies away from dragon/baron with long-range abilities.',
    ],
  },
  'Mage/support': {
    starter: ["Spellthief's Edge", 'Health Potion'],
    core_items: ["Shurelya's Battlesong", "Staff of Flowing Water", "Chemtech Putrifier"],
    boots: "Sorcerer's Shoes",
    situational: ["Zhonya's Hourglass", "Banshee's Veil", 'Redemption'],
    primary_tree: 'Sorcery',
    primary_keystone: 'Arcane Comet',
    primary_slots: ['Manaflow Band', 'Transcendence', 'Scorch'],
    secondary_tree: 'Inspiration',
    secondary_slots: ['Biscuit Delivery', 'Cosmic Insight'],
    skill_first_three: ['Q', 'W', 'E'],
    skill_max_order: ['Q', 'W', 'E'],
    laning_tips: [
      'Poke enemies to proc Spellthief charges and Arcane Comet.',
      'Stand behind minions to avoid enemy skillshots.',
      'Roam mid after shoving the wave with your ADC.',
    ],
    teamfight_tips: [
      'Provide utility and poke from a safe distance.',
      'Use shields/heals to protect priority targets.',
    ],
    objective_tips: [
      'Ward objectives early and sweep enemy vision.',
      'Use long-range abilities to zone enemies from objective pits.',
    ],
  },
  'Assassin/mid': {
    starter: ["Doran's Blade", 'Health Potion'],
    core_items: ['Youmuu\'s Ghostblade', 'Edge of Night', 'Serylda\'s Grudge'],
    boots: "Ionian Boots of Lucidity",
    situational: ["Guardian Angel", "Maw of Malmortius", "Serpent's Fang"],
    primary_tree: 'Domination',
    primary_keystone: 'Electrocute',
    primary_slots: ['Sudden Impact', 'Eyeball Collection', 'Treasure Hunter'],
    secondary_tree: 'Precision',
    secondary_slots: ['Triumph', 'Coup de Grace'],
    skill_first_three: ['Q', 'W', 'E'],
    skill_max_order: ['Q', 'W', 'E'],
    laning_tips: [
      'Look for short burst trades with Electrocute -- back off after proc.',
      'Roam to side lanes after pushing the wave for kill pressure.',
      'Save your escape ability to avoid ganks.',
    ],
    teamfight_tips: [
      'Wait for the fight to start before diving the enemy backline.',
      'Target the squishiest, most fed carry on the enemy team.',
    ],
    objective_tips: [
      'Use roaming windows to secure vision and pick off isolated enemies.',
      'Threaten flanks around dragon and baron to zone carries.',
    ],
  },
  'Assassin/jungle': {
    starter: ['Gustwalker Hatchling'],
    core_items: ['Youmuu\'s Ghostblade', 'Edge of Night', 'Serylda\'s Grudge'],
    boots: "Ionian Boots of Lucidity",
    situational: ["Guardian Angel", "Maw of Malmortius", "Serpent's Fang"],
    primary_tree: 'Domination',
    primary_keystone: 'Electrocute',
    primary_slots: ['Sudden Impact', 'Eyeball Collection', 'Treasure Hunter'],
    secondary_tree: 'Precision',
    secondary_slots: ['Triumph', 'Coup de Grace'],
    skill_first_three: ['Q', 'W', 'E'],
    skill_max_order: ['Q', 'W', 'E'],
    laning_tips: [
      'Full clear one side then gank the closest lane.',
      'Track the enemy jungler by watching which laners are leashing.',
      'Take Rift Scuttler on spawn for vision and gold.',
    ],
    teamfight_tips: [
      'Flank from fog of war to assassinate priority targets.',
      'Do not engage first -- wait for your frontline to absorb cooldowns.',
    ],
    objective_tips: [
      'Prioritize ganking winning lanes to snowball objective control.',
      'Smite-contest dragon and Rift Herald.',
    ],
  },
  'Fighter/jungle': {
    starter: ['Gustwalker Hatchling'],
    core_items: ['Trinity Force', "Sterak's Gage", "Death's Dance"],
    boots: 'Plated Steelcaps',
    situational: ["Guardian Angel", "Maw of Malmortius", "Hullbreaker"],
    primary_tree: 'Precision',
    primary_keystone: 'Conqueror',
    primary_slots: ['Triumph', 'Legend: Tenacity', 'Last Stand'],
    secondary_tree: 'Resolve',
    secondary_slots: ['Conditioning', 'Unflinching'],
    skill_first_three: ['Q', 'W', 'E'],
    skill_max_order: ['Q', 'W', 'E'],
    laning_tips: [
      'Power farm to 6 before looking for ganks with your ultimate.',
      'Track the enemy jungler by watching which laners are leashing.',
      'Prioritize full clears for strong scaling.',
    ],
    teamfight_tips: [
      'Dive the backline or peel depending on team needs.',
      'Fully stack Conqueror before committing to all-ins.',
    ],
    objective_tips: [
      'Contest Rift Herald for early tower pressure.',
      'Solo dragon when the enemy jungler shows on the opposite side of the map.',
    ],
  },
  'Marksman/adc': {
    starter: ["Doran's Blade", 'Health Potion'],
    core_items: ['Infinity Edge', 'Phantom Dancer', 'Bloodthirster'],
    boots: "Berserker's Greaves",
    situational: ["Guardian Angel", "Lord Dominik's Regards", "Mortal Reminder"],
    primary_tree: 'Precision',
    primary_keystone: 'Press the Attack',
    primary_slots: ['Triumph', 'Legend: Bloodline', 'Coup de Grace'],
    secondary_tree: 'Domination',
    secondary_slots: ['Taste of Blood', 'Treasure Hunter'],
    skill_first_three: ['Q', 'W', 'E'],
    skill_max_order: ['Q', 'W', 'E'],
    laning_tips: [
      'Focus on last hitting -- every CS matters for item spikes.',
      'Trade when your support engages and Press the Attack is ready.',
      'Freeze the wave near your tower to stay safe from ganks.',
    ],
    teamfight_tips: [
      'Position behind your frontline and attack the closest safe target.',
      'Do not chase kills -- stay alive and keep dealing damage.',
    ],
    objective_tips: [
      'Stay with your team for dragon fights after first item completion.',
      'Take tower plates whenever the enemy bot lane recalls.',
    ],
  },
  'Support/support': {
    starter: ["Spellthief's Edge", 'Health Potion'],
    core_items: ["Shurelya's Battlesong", 'Redemption', "Ardent Censer"],
    boots: 'Ionian Boots of Lucidity',
    situational: ["Mikael's Blessing", "Staff of Flowing Water", "Chemtech Putrifier"],
    primary_tree: 'Resolve',
    primary_keystone: 'Guardian',
    primary_slots: ['Font of Life', 'Bone Plating', 'Revitalize'],
    secondary_tree: 'Inspiration',
    secondary_slots: ['Biscuit Delivery', 'Cosmic Insight'],
    skill_first_three: ['Q', 'W', 'E'],
    skill_max_order: ['W', 'Q', 'E'],
    laning_tips: [
      'Shield/heal your ADC at the right time to win trades.',
      'Keep river warded to protect from ganks.',
      'Roam mid when your ADC is safe under tower.',
    ],
    teamfight_tips: [
      'Stay near your carries and provide shields/heals.',
      'Use Redemption during teamfights to heal your team.',
    ],
    objective_tips: [
      'Ward dragon/baron pit 60s before spawn time.',
      'Use Oracle Lens to clear enemy vision on objectives.',
    ],
  },
};

// ---------------------------------------------------------------------------
// Helper: resolve the best default key for a champion's tag + role
// ---------------------------------------------------------------------------

function resolveBuildKey(tags: string[], role: Role): string {
  // Attempt exact tag/role match first
  for (const tag of tags) {
    const key = `${tag}/${role}`;
    if (ROLE_BUILD_DEFAULTS[key]) return key;
  }

  // Fall back to role-based defaults
  const roleFallbacks: Record<Role, string> = {
    top: 'Fighter/top',
    jungle: 'Fighter/jungle',
    mid: 'Mage/mid',
    adc: 'Marksman/adc',
    support: 'Support/support',
  };

  return roleFallbacks[role];
}

// ---------------------------------------------------------------------------
// Agent definition
// ---------------------------------------------------------------------------

export const buildAndRunesPlannerAgent: AgentDefinition = {
  name: 'build_and_runes_planner',
  description: 'Generates recommended build, runes, skill order, and tips using FAST MODE hardcoded defaults per champion tag and role.',
  inputSchema: BuildPlannerInputSchema,
  outputSchema: BuildPlannerOutputSchema,

  async execute(input: unknown): Promise<AgentResult> {
    const start = Date.now();
    try {
      const parsed = BuildPlannerInputSchema.parse(input) as BuildPlannerInput;
      const { role, champion_data } = parsed;
      const tags = champion_data.tags;

      const buildKey = resolveBuildKey(tags, role);
      const defaults = ROLE_BUILD_DEFAULTS[buildKey];

      if (!defaults) {
        throw new Error(`No FAST MODE build defaults found for key "${buildKey}"`);
      }

      const recommended_build: RecommendedBuild = {
        starter: defaults.starter,
        core_items: defaults.core_items,
        boots: defaults.boots,
        situational: defaults.situational,
      };

      const recommended_runes: RecommendedRunes = {
        primary_tree: defaults.primary_tree,
        primary_keystone: defaults.primary_keystone,
        primary_slots: defaults.primary_slots,
        secondary_tree: defaults.secondary_tree,
        secondary_slots: defaults.secondary_slots,
      };

      const skill_order: SkillOrder = {
        first_three: defaults.skill_first_three,
        max_order: defaults.skill_max_order,
      };

      const output: BuildPlannerOutput = {
        recommended_build,
        recommended_runes,
        skill_order,
        laning_tips: defaults.laning_tips,
        teamfight_tips: defaults.teamfight_tips,
        objective_tips: defaults.objective_tips,
      };

      const validated = BuildPlannerOutputSchema.parse(output);

      return {
        agent: 'build_and_runes_planner',
        success: true,
        data: validated,
        duration_ms: Date.now() - start,
      };
    } catch (err) {
      return {
        agent: 'build_and_runes_planner',
        success: false,
        data: null,
        errors: [err instanceof Error ? err.message : String(err)],
        duration_ms: Date.now() - start,
      };
    }
  },
};

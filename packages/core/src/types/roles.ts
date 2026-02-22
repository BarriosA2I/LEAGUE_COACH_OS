export const ROLES = ['top', 'jungle', 'mid', 'adc', 'support'] as const;
export type Role = (typeof ROLES)[number];

export const ROLE_TAG_MAP: Record<string, Role[]> = {
  Fighter: ['top', 'jungle'],
  Tank: ['top', 'support'],
  Mage: ['mid'],
  Assassin: ['mid', 'jungle'],
  Marksman: ['adc'],
  Support: ['support'],
};

export function inferRoles(tags: string[]): Role[] {
  const roles = new Set<Role>();
  for (const tag of tags) {
    const mapped = ROLE_TAG_MAP[tag];
    if (mapped) mapped.forEach((r) => roles.add(r));
  }
  return [...roles];
}

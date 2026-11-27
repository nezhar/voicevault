import { Capability, User } from '../types';

// Without capability data (an older API) these follow the admin flag, as they
// did before capabilities existed; everything else is shown.
const ADMIN_ONLY: ReadonlySet<Capability> = new Set([
  'admin.view',
  'admin.manage',
  'templates.manage',
]);

const legacyAllows = (user: User, capability: Capability): boolean =>
  ADMIN_ONLY.has(capability) ? user.is_admin : true;

/**
 * Whether the user may use a feature, globally or in one project.
 *
 * Mirrors the API's rule: a capability holds when it is granted globally, or -
 * for project-scoped ones - in that project. A user object without capability
 * data (an older API) is treated as allowed: the API decides either way, the UI
 * only hides what would be refused.
 */
export const can = (
  user: User | null | undefined,
  capability: Capability,
  projectId?: string | null,
): boolean => {
  if (!user) return false;
  if (!user.capabilities) return legacyAllows(user, capability);
  if (user.capabilities.includes(capability)) return true;
  if (!projectId) return false;
  return user.project_capabilities?.[projectId]?.includes(capability) ?? false;
};

/** Whether the capability holds anywhere: globally or in at least one project. */
export const canAnywhere = (user: User | null | undefined, capability: Capability): boolean => {
  if (!user) return false;
  if (!user.capabilities) return legacyAllows(user, capability);
  if (user.capabilities.includes(capability)) return true;
  return Object.values(user.project_capabilities ?? {}).some((caps) => caps.includes(capability));
};

/** Capabilities the user holds anywhere - what a token they create may carry. */
export const heldCapabilities = (user: User | null | undefined): Set<Capability> => {
  const held = new Set<Capability>(user?.capabilities ?? []);
  Object.values(user?.project_capabilities ?? {}).forEach((caps) =>
    caps.forEach((cap) => held.add(cap)),
  );
  return held;
};

// Old token scopes, shown with their meaning on tokens created before
// capabilities existed.
export const LEGACY_SCOPE_LABELS: Record<string, string> = {
  'entries:read': 'Read entries (legacy)',
  'entries:write': 'Write entries (legacy)',
  'projects:read': 'Read projects (legacy)',
  'projects:write': 'Write projects (legacy)',
  'templates:read': 'Read templates (legacy)',
  'templates:write': 'Write templates (legacy)',
  'admin:read': 'Read admin data (legacy)',
};

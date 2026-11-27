import { describe, expect, it } from 'vitest';

import { User } from '../types';
import { can, canAnywhere, heldCapabilities } from './capabilities';

const base: User = { id: 'u', email: 'u@x', display_name: 'U', is_admin: false };

describe('can', () => {
  it('honours global and per-project grants', () => {
    const user: User = {
      ...base,
      capabilities: ['entries.view'],
      project_capabilities: { p1: ['entries.chat'] },
    };
    expect(can(user, 'entries.view')).toBe(true);
    expect(can(user, 'entries.view', 'p2')).toBe(true);
    expect(can(user, 'entries.chat')).toBe(false);
    expect(can(user, 'entries.chat', 'p1')).toBe(true);
    expect(can(user, 'entries.chat', 'p2')).toBe(false);
    expect(canAnywhere(user, 'entries.chat')).toBe(true);
    expect([...heldCapabilities(user)].sort()).toEqual(['entries.chat', 'entries.view']);
  });

  it('falls back to the admin flag for admin features on older APIs', () => {
    expect(can(base, 'entries.chat')).toBe(true);
    expect(can(base, 'templates.manage')).toBe(false);
    expect(can({ ...base, is_admin: true }, 'admin.view')).toBe(true);
    expect(can(null, 'entries.view')).toBe(false);
  });
});

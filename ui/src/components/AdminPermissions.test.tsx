import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CapabilityInfo } from '../types';
import { AdminGroups } from './AdminGroups';
import { AdminPermissions } from './AdminPermissions';

const admin = vi.hoisted(() => ({
  listGroups: vi.fn(),
  getGroup: vi.fn(),
  createGroup: vi.fn(),
  updateGroup: vi.fn(),
  deleteGroup: vi.fn(),
  addGroupMember: vi.fn(),
  removeGroupMember: vi.fn(),
  getGrants: vi.fn(),
  setGrants: vi.fn(),
  getUserPermissions: vi.fn(),
  getPATUsers: vi.fn(),
  searchProjects: vi.fn(),
}));

vi.mock('../services/api', () => ({ adminApi: admin }));

const catalog: CapabilityInfo[] = [
  {
    name: 'entries.chat',
    label: 'Chat',
    area: 'AI',
    description: 'Chat with a transcript',
    project_scoped: true,
    routes: [],
    tools: [],
  },
  {
    name: 'tokens.create',
    label: 'Create access tokens',
    area: 'Integrations',
    description: 'Create tokens',
    project_scoped: false,
    routes: [],
    tools: [],
  },
];

const everyone = {
  id: 'g-everyone',
  name: 'Everyone',
  description: null,
  idp_group: null,
  is_builtin: true,
  member_count: null,
};
const sales = { ...everyone, id: 'g-sales', name: 'Sales', is_builtin: false, member_count: 2 };

beforeEach(() => {
  Object.values(admin).forEach((fn) => fn.mockReset());
  admin.listGroups.mockResolvedValue([everyone, sales]);
  admin.getPATUsers.mockResolvedValue([]);
  admin.searchProjects.mockResolvedValue([]);
});

describe('AdminPermissions', () => {
  it('shows inherited grants shaded and saves only the subject’s own', async () => {
    admin.getGrants.mockResolvedValue([
      { capability: 'entries.chat', project_id: 'p1', project_name: 'Team' },
    ]);
    admin.getUserPermissions.mockResolvedValue({
      user_id: 'u1',
      is_admin: false,
      capabilities: ['tokens.create'],
      project_capabilities: {},
      grants: [
        { capability: 'tokens.create', project_id: null, source: 'Everyone' },
        { capability: 'entries.chat', project_id: 'p1', project_name: 'Team', source: 'user' },
      ],
      groups: ['Everyone'],
    });
    admin.setGrants.mockResolvedValue([]);

    render(
      <AdminPermissions
        catalog={catalog}
        subject={{ kind: 'user', id: 'u1', label: 'Ada' }}
        onSubjectChange={() => undefined}
        canManage
      />,
    );

    const inherited = await screen.findByLabelText('Create access tokens globally');
    expect(inherited.closest('td')).toHaveAttribute('title', 'From Everyone');
    expect(screen.getByLabelText('Chat in Team')).toBeChecked();
    // A global-only capability has no project cell.
    expect(screen.getByTitle('Global only')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Chat globally'));
    fireEvent.click(screen.getByRole('button', { name: 'Save permissions' }));

    await waitFor(() =>
      expect(admin.setGrants).toHaveBeenCalledWith(
        { userId: 'u1' },
        expect.arrayContaining([
          { capability: 'entries.chat', project_id: 'p1' },
          { capability: 'entries.chat', project_id: null },
        ]),
      ),
    );
    expect(admin.setGrants.mock.calls[0][1]).toHaveLength(2);
  });

  it('is read-only without admin.manage', async () => {
    admin.getGrants.mockResolvedValue([]);
    render(
      <AdminPermissions
        catalog={catalog}
        subject={{ kind: 'group', id: 'g-sales', label: 'Sales' }}
        onSubjectChange={() => undefined}
        canManage={false}
      />,
    );
    expect(await screen.findByLabelText('Chat globally')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Save permissions' })).not.toBeInTheDocument();
  });
});

describe('AdminGroups', () => {
  it('creates a group linked to an IdP group', async () => {
    admin.createGroup.mockResolvedValue({ ...sales, id: 'g-new', name: 'Support', members: [] });
    render(<AdminGroups />);

    fireEvent.click(await screen.findByRole('button', { name: 'New group' }));
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Support' } });
    fireEvent.change(screen.getByLabelText(/^IdP group/), { target: { value: 'support-team' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create group' }));

    await waitFor(() =>
      expect(admin.createGroup).toHaveBeenCalledWith({
        name: 'Support',
        description: null,
        idp_group: 'support-team',
      }),
    );
  });

  it('keeps IdP members read-only and protects Everyone', async () => {
    admin.getGroup.mockImplementation(async (id: string) =>
      id === 'g-sales'
        ? {
            ...sales,
            members: [
              { user_id: 'u1', email: 'a@x', display_name: 'A', source: 'idp' },
              { user_id: 'u2', email: 'b@x', display_name: 'B', source: 'manual' },
            ],
          }
        : { ...everyone, members: [] },
    );
    render(<AdminGroups />);

    fireEvent.click(await screen.findByText('Sales'));
    expect(await screen.findByText('IdP')).toBeInTheDocument();
    expect(screen.queryByLabelText('Remove a@x')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Remove b@x')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Everyone'));
    await waitFor(() => expect(screen.getByLabelText('Name')).toBeDisabled());
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
  });
});

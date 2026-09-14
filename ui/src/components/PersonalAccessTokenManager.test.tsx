import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { formatDateTime } from '../utils/format';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PATPermission } from '../types';
import { statusOf } from '../utils/tokens';
import { PersonalAccessTokenManager } from './PersonalAccessTokenManager';

const api = vi.hoisted(() => ({
  listPATs: vi.fn(),
  createPAT: vi.fn(),
  updatePAT: vi.fn(),
  revokePAT: vi.fn(),
}));

const admin = vi.hoisted(() => ({
  getPATUsers: vi.fn(),
  getPATs: vi.fn(),
  revokePAT: vi.fn(),
}));

vi.mock('../services/api', () => ({ authApi: api, adminApi: admin }));

const token = {
  id: 'pat-1',
  name: 'CI',
  token_prefix: 'vvpat_abcdefghij',
  permissions: ['entries:read'] as PATPermission[],
  created_at: '2026-09-04T12:00:00Z',
  expires_at: null,
  last_used_at: null,
  revoked_at: null,
};

const revokedToken = {
  ...token,
  id: 'pat-2',
  name: 'Old laptop',
  revoked_at: '2026-09-05T12:00:00Z',
};

const currentUser = {
  id: 'user-1',
  email: 'ada@example.com',
  display_name: 'Ada',
  is_admin: false,
  is_active: true,
};

const adminUser = { ...currentUser, is_admin: true };

const emptyPage = { tokens: [], total: 0, page: 1, per_page: 25, total_pages: 0 };

const fillCreateForm = (name: string) => {
  fireEvent.change(screen.getByPlaceholderText('CI pipeline'), { target: { value: name } });
  fireEvent.click(screen.getByLabelText(/Read entries/));
  fireEvent.click(screen.getByRole('button', { name: 'Create token' }));
};

describe('statusOf', () => {
  const now = new Date('2026-09-07T00:00:00Z').getTime();

  it('reads a zone-less expiry as UTC, so the row keeps its controls', () => {
    vi.stubEnv('TZ', 'Europe/Berlin'); // UTC+2: local parsing would expire it early
    try {
      expect(statusOf({ ...token, expires_at: '2026-09-07T01:00:00' }, now)).toBe('active');
      expect(statusOf({ ...token, expires_at: '2026-09-06T23:00:00' }, now)).toBe('expired');
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it('ranks revoked above expired above active', () => {
    expect(statusOf(token, now)).toBe('active');
    expect(statusOf({ ...token, expires_at: '2026-09-01T00:00:00Z' }, now)).toBe('expired');
    expect(
      statusOf(
        { ...token, expires_at: '2026-09-01T00:00:00Z', revoked_at: '2026-08-01T00:00:00Z' },
        now,
      ),
    ).toBe('revoked');
  });
});

describe('PersonalAccessTokenManager', () => {
  beforeEach(() => {
    api.listPATs.mockReset().mockResolvedValue([]);
    api.createPAT.mockReset();
    api.updatePAT.mockReset();
    api.revokePAT.mockReset().mockResolvedValue(undefined);
    admin.getPATUsers.mockReset().mockResolvedValue([]);
    admin.getPATs.mockReset().mockResolvedValue(emptyPage);
    admin.revokePAT.mockReset().mockResolvedValue(undefined);
    vi.restoreAllMocks();
  });

  it('shows the create form before the token list', () => {
    render(<PersonalAccessTokenManager currentUser={currentUser} isAdmin={false} />);

    const headings = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent);
    expect(headings[0]).toBe('Create a token');
    expect(headings[1]).toMatch(/^Your tokens/);
  });

  it('shows a newly created token once, with a ready-to-run curl example', async () => {
    api.createPAT.mockResolvedValue({ ...token, token: 'vvpat_full-secret' });
    render(<PersonalAccessTokenManager currentUser={currentUser} isAdmin={false} />);

    fillCreateForm('CI');

    await waitFor(() => expect(api.createPAT).toHaveBeenCalled());
    expect(screen.getByText('vvpat_full-secret')).toBeInTheDocument();
    expect(screen.getByText(/will not be shown again/i)).toBeInTheDocument();
    const callout = screen.getByRole('status');
    const example = within(callout).getAllByText(/^curl /)[0].textContent ?? '';
    expect(example).toContain('Authorization: Bearer vvpat_full-secret');
    expect(example).toContain(`${window.location.origin}/api/entries/`);
    expect(within(callout).getByRole('button', { name: 'Copy list example' })).toBeInTheDocument();
  });

  it('lets the user switch the created-token guide to MCP', async () => {
    api.createPAT.mockResolvedValue({ ...token, token: 'vvpat_full-secret' });
    render(<PersonalAccessTokenManager currentUser={currentUser} isAdmin={false} mcpEnabled />);

    fillCreateForm('CI');
    await waitFor(() => expect(api.createPAT).toHaveBeenCalled());
    const callout = screen.getByRole('status');
    fireEvent.click(within(callout).getByRole('button', { name: 'MCP' }));

    const config = within(callout).getByTestId('mcp-config').textContent ?? '';
    expect(config).toContain(`${window.location.origin}/mcp`);
    expect(config).toContain('Bearer vvpat_full-secret');
  });

  it('keeps a collapsed guide with a placeholder token below the create form', () => {
    render(<PersonalAccessTokenManager currentUser={currentUser} isAdmin={false} />);

    const guide = screen.getByText('How to use a token').closest('details');
    expect(guide).not.toBeNull();
    expect(guide).not.toHaveAttribute('open');
    const example = within(guide as HTMLElement).getAllByText(/^curl /)[0].textContent ?? '';
    expect(example).toContain('Bearer vvpat_…');
    // Heading order is unchanged: the guide is not a section of its own.
    const headings = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent);
    expect(headings[0]).toBe('Create a token');
    expect(headings[1]).toMatch(/^Your tokens/);
  });

  it('tells the user when MCP is disabled on this server', () => {
    render(
      <PersonalAccessTokenManager currentUser={currentUser} isAdmin={false} mcpEnabled={false} />,
    );

    const guide = screen.getByText('How to use a token').closest('details') as HTMLElement;
    fireEvent.click(within(guide).getByRole('button', { name: 'MCP' }));
    expect(within(guide).getByRole('note')).toHaveTextContent('MCP_ENABLED=true');
  });

  it('creates tokens for the signed-in user even when an admin is viewing all tokens', async () => {
    api.createPAT.mockResolvedValue({ ...token, name: 'Deploy', token: 'vvpat_secret' });
    render(<PersonalAccessTokenManager currentUser={adminUser} isAdmin />);

    fireEvent.click(screen.getByRole('button', { name: 'All tokens' }));
    fillCreateForm('Deploy');

    await waitFor(() =>
      expect(api.createPAT).toHaveBeenCalledWith({
        name: 'Deploy',
        permissions: ['entries:read'],
        expires_at: null,
      }),
    );
    expect(screen.getByText(/acts as/).textContent).toContain(adminUser.email);
    // the list jumps back to the admin's own tokens so the new one is visible
    await waitFor(() =>
      expect(admin.getPATs).toHaveBeenLastCalledWith(
        expect.objectContaining({ userId: adminUser.id, status: 'active', page: 1 }),
      ),
    );
  });

  it('hides the admin-only permission and the scope switch from normal users', () => {
    render(<PersonalAccessTokenManager currentUser={currentUser} isAdmin={false} />);

    expect(screen.queryByLabelText(/Read admin data/)).not.toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Token scope' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Filter by user')).not.toBeInTheDocument();
    expect(admin.getPATs).not.toHaveBeenCalled();
  });

  it('shows only active tokens by default and can widen to all statuses', async () => {
    api.listPATs.mockResolvedValue([token, revokedToken]);
    render(<PersonalAccessTokenManager currentUser={currentUser} isAdmin={false} />);

    await screen.findByText('CI');
    expect(screen.queryByText('Old laptop')).not.toBeInTheDocument();
    expect(screen.getByText(/^Your tokens/).textContent).toContain('(1)');

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'all' } });

    expect(await screen.findByText('Old laptop')).toBeInTheDocument();
    expect(screen.getByText(/^Your tokens/).textContent).toContain('(2)');
  });

  it('shows a status badge per token and no revoke action for revoked ones', async () => {
    api.listPATs.mockResolvedValue([token, revokedToken]);
    render(<PersonalAccessTokenManager currentUser={currentUser} isAdmin={false} />);

    await screen.findByText('CI');
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'all' } });
    await screen.findByText('Old laptop');

    const rows = screen.getAllByRole('listitem');
    expect(within(rows[0]).getByText('Active')).toBeInTheDocument();
    expect(within(rows[0]).getByRole('button', { name: 'Revoke' })).toBeInTheDocument();
    expect(within(rows[1]).getByText('Revoked')).toBeInTheDocument();
    expect(within(rows[1]).queryByRole('button', { name: 'Revoke' })).not.toBeInTheDocument();
  });

  it('offers to clear the filters when nothing matches', async () => {
    api.listPATs.mockResolvedValue([revokedToken]);
    render(<PersonalAccessTokenManager currentUser={currentUser} isAdmin={false} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Show all tokens' }));

    expect(await screen.findByText('Old laptop')).toBeInTheDocument();
  });

  it('shows the exact expiry date together with the relative time', async () => {
    const expiresAt = new Date(Date.now() + 3 * 86400000).toISOString();
    api.listPATs.mockResolvedValue([
      token,
      { ...token, id: 'pat-3', name: 'Expiring', expires_at: expiresAt },
    ]);
    render(<PersonalAccessTokenManager currentUser={currentUser} isAdmin={false} />);

    await screen.findByText('Expiring');
    expect(screen.getByText('Never expires')).toBeInTheDocument();
    expect(
      screen.getByText(`Expires ${formatDateTime(expiresAt)} (in 3 days)`),
    ).toBeInTheDocument();
  });

  it('revokes an owned token only after the dialog is confirmed', async () => {
    api.listPATs.mockResolvedValue([token]);
    render(<PersonalAccessTokenManager currentUser={currentUser} isAdmin={false} />);

    await screen.findByText('CI');
    fireEvent.click(screen.getByRole('button', { name: 'Revoke' }));

    const dialog = screen.getByRole('dialog', { name: 'Revoke “CI”?' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(api.revokePAT).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Revoke' }));
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Revoke token' }),
    );

    await waitFor(() => expect(api.revokePAT).toHaveBeenCalledWith('pat-1'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('renames a token and changes its expiry, sending only what changed', async () => {
    api.listPATs.mockResolvedValue([token]);
    api.updatePAT.mockResolvedValue({ ...token, name: 'CI (renamed)' });
    render(<PersonalAccessTokenManager currentUser={currentUser} isAdmin={false} />);

    await screen.findByText('CI');
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    const editor = screen.getByRole('form', { name: 'Edit CI' });
    const save = within(editor).getByRole('button', { name: 'Save' });
    expect(save).toBeDisabled(); // nothing changed yet

    fireEvent.change(within(editor).getByLabelText('Name'), { target: { value: 'CI (renamed)' } });
    fireEvent.click(save);

    await waitFor(() =>
      expect(api.updatePAT).toHaveBeenCalledWith('pat-1', { name: 'CI (renamed)' }),
    );
    expect(await screen.findByText('CI (renamed)')).toBeInTheDocument();
    expect(screen.queryByRole('form', { name: /Edit/ })).not.toBeInTheDocument();
  });

  it('does not touch the expiry of a token that has one when only the name changes', async () => {
    // The API sends sub-second UTC; the input edits minute-precision local time.
    // Comparing the two representations directly marked the expiry dirty on every
    // token that had one, so a rename silently rewrote it.
    const expiring = {
      ...token,
      expires_at: new Date(Date.now() + 30 * 86400000).toISOString().replace(/\.\d+Z$/, '.123456Z'),
    };
    api.listPATs.mockResolvedValue([expiring]);
    api.updatePAT.mockResolvedValue({ ...expiring, name: 'CI (renamed)' });
    render(<PersonalAccessTokenManager currentUser={currentUser} isAdmin={false} />);

    await screen.findByText('CI');
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    const editor = screen.getByRole('form', { name: 'Edit CI' });
    const save = within(editor).getByRole('button', { name: 'Save' });
    expect(save).toBeDisabled(); // an untouched form is not dirty

    fireEvent.change(within(editor).getByLabelText('Name'), { target: { value: 'CI (renamed)' } });
    fireEvent.click(save);

    await waitFor(() =>
      expect(api.updatePAT).toHaveBeenCalledWith('pat-1', { name: 'CI (renamed)' }),
    );
  });

  it('clears an expiry with the Never preset', async () => {
    const expiresAt = new Date(Date.now() + 30 * 86400000).toISOString();
    api.listPATs.mockResolvedValue([{ ...token, expires_at: expiresAt }]);
    api.updatePAT.mockResolvedValue({ ...token, expires_at: null });
    render(<PersonalAccessTokenManager currentUser={currentUser} isAdmin={false} />);

    await screen.findByText('CI');
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    const editor = screen.getByRole('form', { name: 'Edit CI' });
    fireEvent.click(within(editor).getByRole('button', { name: 'Never' }));
    fireEvent.click(within(editor).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(api.updatePAT).toHaveBeenCalledWith('pat-1', { expires_at: null }));
    expect(await screen.findByText('Never expires')).toBeInTheDocument();
  });

  it('drops a superseded response instead of overwriting the newer rows', async () => {
    const mine = { ...emptyPage, tokens: [token], total: 1, total_pages: 1 };
    const all = {
      ...emptyPage,
      tokens: [{ ...token, id: 'pat-9', name: 'Grace key' }],
      total: 1,
      total_pages: 1,
    };
    let releaseFirst: (value: typeof mine) => void = () => {};
    admin.getPATs
      .mockImplementationOnce(() => new Promise((resolve) => (releaseFirst = resolve)))
      .mockResolvedValueOnce(all);

    render(<PersonalAccessTokenManager currentUser={adminUser} isAdmin />);
    fireEvent.click(screen.getByRole('button', { name: 'All tokens' }));

    expect(await screen.findByText('Grace key')).toBeInTheDocument();

    // The request for the old scope answers last. Its rows belong to a heading
    // and a filter that are no longer on screen, so they must be discarded.
    await act(async () => {
      releaseFirst(mine);
    });

    expect(screen.getByText('Grace key')).toBeInTheDocument();
    expect(screen.queryByText('CI')).not.toBeInTheDocument();
  });

  it('does not offer to edit other users tokens or inactive ones', async () => {
    const grace = {
      id: 'user-2',
      email: 'grace@example.com',
      display_name: 'Grace',
      is_active: true,
    };
    admin.getPATs.mockResolvedValue({
      tokens: [
        { ...token, user: { ...currentUser, is_active: true } },
        { ...token, id: 'pat-2', name: 'Graces token', user: grace },
        { ...revokedToken, user: { ...currentUser, is_active: true } },
      ],
      total: 3,
      page: 1,
      per_page: 25,
      total_pages: 1,
    });
    render(<PersonalAccessTokenManager currentUser={adminUser} isAdmin />);

    await screen.findByText('Graces token');
    const rows = screen.getAllByRole('listitem');
    expect(within(rows[0]).getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(within(rows[1]).queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(within(rows[1]).getByRole('button', { name: 'Revoke' })).toBeInTheDocument();
    expect(within(rows[2]).queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
  });

  it('starts admins on their own active tokens', async () => {
    render(<PersonalAccessTokenManager currentUser={adminUser} isAdmin />);

    await waitFor(() =>
      expect(admin.getPATs).toHaveBeenCalledWith({
        userId: adminUser.id,
        name: undefined,
        status: 'active',
        page: 1,
        perPage: 25,
      }),
    );
    expect(screen.getByRole('button', { name: 'My tokens' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.queryByLabelText('Filter by user')).not.toBeInTheDocument();
  });

  it('lets an admin switch to all tokens and narrow them to one user', async () => {
    const otherUser = {
      id: 'user-2',
      email: 'grace@example.com',
      display_name: 'Grace',
      is_active: true,
    };
    admin.getPATUsers.mockResolvedValue([otherUser]);
    render(<PersonalAccessTokenManager currentUser={adminUser} isAdmin />);

    fireEvent.click(screen.getByRole('button', { name: 'All tokens' }));
    await waitFor(() =>
      expect(admin.getPATs).toHaveBeenLastCalledWith(
        expect.objectContaining({ userId: undefined }),
      ),
    );

    fireEvent.change(screen.getByLabelText('Filter by user'), { target: { value: 'grace' } });
    await waitFor(() => expect(admin.getPATUsers).toHaveBeenCalledWith('grace'));
    fireEvent.click(await screen.findByRole('option', { name: /Grace/ }));

    await waitFor(() =>
      expect(admin.getPATs).toHaveBeenLastCalledWith(
        expect.objectContaining({ userId: otherUser.id, page: 1, perPage: 25 }),
      ),
    );
    expect(screen.getByText(/^Tokens of Grace/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Clear user filter' }));
    await waitFor(() =>
      expect(admin.getPATs).toHaveBeenLastCalledWith(
        expect.objectContaining({ userId: undefined }),
      ),
    );
  });

  it('requests the next bounded page of admin tokens', async () => {
    admin.getPATs.mockResolvedValue({
      tokens: [{ ...token, user: { ...currentUser, is_active: true } }],
      total: 51,
      page: 1,
      per_page: 25,
      total_pages: 3,
    });
    render(<PersonalAccessTokenManager currentUser={adminUser} isAdmin />);

    await screen.findByText('CI');
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    await waitFor(() =>
      expect(admin.getPATs).toHaveBeenCalledWith(expect.objectContaining({ page: 2, perPage: 25 })),
    );
  });
});

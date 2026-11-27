import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { OAuthConsent } from './OAuthConsent';

const oauthApi = vi.hoisted(() => ({ getRequest: vi.fn(), approve: vi.fn(), deny: vi.fn() }));
const capabilityApi = vi.hoisted(() => ({ list: vi.fn() }));
const projectApi = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock('../services/api', () => ({ oauthApi, capabilityApi, projectApi }));

const user = vi.hoisted(() => ({
  id: 'u1',
  email: 'ada@example.com',
  display_name: 'Ada',
  is_admin: false,
  capabilities: ['entries.view', 'entries.chat', 'mcp.connect'],
}));
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user }) }));

const catalog = ['entries.view', 'entries.chat', 'entries.delete', 'mcp.connect'].map((name) => ({
  name,
  label: name,
  area: 'Entries',
  description: '',
  project_scoped: name !== 'mcp.connect',
  routes: [],
  tools: [],
}));

const assign = vi.fn();

beforeEach(() => {
  window.location.hash = '#req-1';
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, hash: '#req-1', assign },
  });
  oauthApi.getRequest.mockReset().mockResolvedValue({
    id: 'req-1',
    client_name: 'Claude',
    redirect_uri: 'https://claude.ai/api/mcp/auth_callback',
    requested_capabilities: [],
    expires_at: '2026-11-26T12:00:00Z',
  });
  oauthApi.approve.mockReset().mockResolvedValue({ redirect_to: 'https://claude.ai/cb?code=x' });
  oauthApi.deny.mockReset().mockResolvedValue({ redirect_to: 'https://claude.ai/cb?error=x' });
  capabilityApi.list.mockReset().mockResolvedValue(catalog);
  projectApi.list.mockReset().mockResolvedValue([]);
  assign.mockReset();
});

afterEach(() => vi.restoreAllMocks());

describe('OAuthConsent', () => {
  it('names the client and the return address, and approves the default selection', async () => {
    render(<OAuthConsent />);
    expect(await screen.findByText('Claude')).toBeInTheDocument();
    expect(screen.getByText('https://claude.ai/api/mcp/auth_callback')).toBeInTheDocument();
    // a capability the user does not hold cannot be ticked
    expect(screen.getByLabelText(/entries.delete/)).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    await waitFor(() =>
      expect(oauthApi.approve).toHaveBeenCalledWith('req-1', {
        permissions: ['entries.view', 'entries.chat', 'mcp.connect'],
        project_ids: null,
      }),
    );
    expect(assign).toHaveBeenCalledWith('https://claude.ai/cb?code=x');
  });

  it('denies', async () => {
    render(<OAuthConsent />);
    fireEvent.click(await screen.findByRole('button', { name: 'Deny' }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith('https://claude.ai/cb?error=x'));
  });

  it('explains an expired request', async () => {
    oauthApi.getRequest.mockRejectedValue(
      Object.assign(new Error('gone'), { isAxiosError: true, response: { status: 404 } }),
    );
    render(<OAuthConsent />);
    expect(await screen.findByText(/expired or was already decided/)).toBeInTheDocument();
  });
});

import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { User } from './types';

const { getEntries, getPromptTemplates, listProjects, authState } = vi.hoisted(() => ({
  getEntries: vi.fn(),
  getPromptTemplates: vi.fn(),
  listProjects: vi.fn(),
  authState: { user: null as User | null },
}));

vi.mock('./services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./services/api')>();
  return {
    ...actual,
    entryApi: { ...actual.entryApi, getEntries, getPromptTemplates },
    projectApi: { ...actual.projectApi, list: listProjects },
  };
});

vi.mock('./context/AuthContext', () => ({
  useAuth: () => ({
    mode: 'oidc',
    user: authState.user,
    isLoading: false,
    isAuthenticated: authState.user !== null,
    loginWithToken: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  }),
}));

const member: User = {
  id: 'u1',
  email: 'bob@corp.com',
  display_name: 'Bob',
  is_admin: false,
};

const admin: User = { ...member, id: 'u2', email: 'ada@corp.com', is_admin: true };

const templateButton = () =>
  screen.queryByRole('button', { name: 'Open prompt template settings' });

describe('App prompt template configurator', () => {
  beforeEach(() => {
    getEntries.mockReset().mockResolvedValue({ entries: [], total: 0 });
    getPromptTemplates.mockReset().mockResolvedValue([]);
    listProjects.mockReset().mockResolvedValue([]);
  });

  it('hides the configurator from non-admins and never fetches the full list', async () => {
    authState.user = member;

    render(<App />);
    await waitFor(() => expect(getEntries).toHaveBeenCalled());

    expect(templateButton()).not.toBeInTheDocument();
    expect(getPromptTemplates).not.toHaveBeenCalled();
  });

  it('offers the configurator to admins, backed by the full template list', async () => {
    authState.user = admin;

    render(<App />);
    await waitFor(() => expect(getEntries).toHaveBeenCalled());

    expect(templateButton()).toBeInTheDocument();
    expect(getPromptTemplates).toHaveBeenCalledWith(false);
  });
});

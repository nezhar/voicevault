import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { Login } from './Login';

const mockUseAuth = vi.fn();

vi.mock('../context/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

describe('Login', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
  });

  it('renders an SSO link in oidc mode', () => {
    mockUseAuth.mockReturnValue({ mode: 'oidc', loginWithToken: vi.fn() });

    render(<Login />);

    const link = screen.getByText('Sign in with SSO').closest('a');
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/api/auth/oidc/login');
  });

  it('submits the token form in token mode', async () => {
    const loginWithToken = vi.fn().mockResolvedValue(undefined);
    mockUseAuth.mockReturnValue({ mode: 'token', loginWithToken });

    render(<Login />);

    fireEvent.change(screen.getByPlaceholderText('Enter your access token'), {
      target: { value: 'secret-token' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Access Application' }));

    await waitFor(() => expect(loginWithToken).toHaveBeenCalledWith('secret-token'));
  });
});

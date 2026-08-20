import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ProjectAccessRequest } from './ProjectAccessRequest';
import { projectApi } from '../services/api';
import { ProjectPreview } from '../types';

vi.mock('../services/api', () => ({
  projectApi: {
    preview: vi.fn(),
    requestAccess: vi.fn(),
    cancelRequest: vi.fn(),
  },
}));

const basePreview: ProjectPreview = {
  id: 'p1',
  name: 'Team Alpha',
  owners: [{ display_name: 'Ada', email: 'ada@corp' }],
  my_role: null,
  request_status: null,
  request_id: null,
  can_request: true,
};

const mocked = vi.mocked(projectApi);

describe('ProjectAccessRequest', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the project name, owners and a request button', async () => {
    mocked.preview.mockResolvedValue(basePreview);
    render(<ProjectAccessRequest projectId="p1" onAccessGranted={vi.fn()} />);

    expect(await screen.findByText('Team Alpha')).toBeInTheDocument();
    expect(screen.getByText(/ada@corp/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Request access' })).toBeInTheDocument();
  });

  it('sends the note with the request and switches to pending', async () => {
    mocked.preview.mockResolvedValue(basePreview);
    mocked.requestAccess.mockResolvedValue({
      id: 'r1',
      project_id: 'p1',
      user_id: 'u1',
      email: 'me@corp',
      display_name: 'Me',
      status: 'pending',
      message: 'joining the QBR team',
      created_at: '2026-08-20T10:00:00Z',
      decided_at: null,
      decided_by_name: null,
    });

    render(<ProjectAccessRequest projectId="p1" onAccessGranted={vi.fn()} />);
    fireEvent.change(await screen.findByPlaceholderText(/why do you need access/i), {
      target: { value: 'joining the QBR team' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Request access' }));

    await waitFor(() =>
      expect(mocked.requestAccess).toHaveBeenCalledWith('p1', 'joining the QBR team'),
    );
    expect(await screen.findByText(/waiting for an owner/i)).toBeInTheDocument();
  });

  it('offers to cancel a pending request', async () => {
    mocked.preview.mockResolvedValue({
      ...basePreview,
      request_status: 'pending',
      request_id: 'r1',
    });
    mocked.cancelRequest.mockResolvedValue(undefined);

    render(<ProjectAccessRequest projectId="p1" onAccessGranted={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel request' }));

    await waitFor(() => expect(mocked.cancelRequest).toHaveBeenCalledWith('p1', 'r1'));
    expect(await screen.findByRole('button', { name: 'Request access' })).toBeInTheDocument();
  });

  it('lets a denied user try again', async () => {
    mocked.preview.mockResolvedValue({
      ...basePreview,
      request_status: 'denied',
      request_id: 'r1',
    });

    render(<ProjectAccessRequest projectId="p1" onAccessGranted={vi.fn()} />);

    expect(await screen.findByText(/was declined/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Request again' })).toBeInTheDocument();
  });

  it('notifies the parent once access has been granted', async () => {
    const onAccessGranted = vi.fn();
    mocked.preview.mockResolvedValue({
      ...basePreview,
      my_role: 'viewer',
      request_status: 'approved',
      request_id: 'r1',
      can_request: false,
    });

    render(<ProjectAccessRequest projectId="p1" onAccessGranted={onAccessGranted} />);

    await waitFor(() => expect(onAccessGranted).toHaveBeenCalled());
  });

  it('hides the request control when the deployment does not support it', async () => {
    mocked.preview.mockResolvedValue({ ...basePreview, can_request: false });

    render(<ProjectAccessRequest projectId="p1" onAccessGranted={vi.fn()} />);

    expect(await screen.findByText('Team Alpha')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Request access' })).not.toBeInTheDocument();
  });

  it('explains a missing project', async () => {
    mocked.preview.mockRejectedValue(new Error('404'));

    render(<ProjectAccessRequest projectId="p1" onAccessGranted={vi.fn()} />);

    expect(await screen.findByText(/no longer available/i)).toBeInTheDocument();
  });
});

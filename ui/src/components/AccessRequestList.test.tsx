import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AccessRequestList } from './AccessRequestList';
import { projectApi } from '../services/api';
import { AccessRequest } from '../types';

vi.mock('../services/api', () => ({
  projectApi: {
    listAccessRequests: vi.fn(),
    approveRequest: vi.fn(),
    denyRequest: vi.fn(),
  },
}));

const pendingRequest: AccessRequest = {
  id: 'r1',
  project_id: 'p1',
  user_id: 'u2',
  email: 'bob@corp',
  display_name: 'Bob',
  status: 'pending',
  message: 'joining the QBR team',
  created_at: '2026-08-20T10:00:00Z',
  decided_at: null,
  decided_by_name: null,
};

const mocked = vi.mocked(projectApi);

describe('AccessRequestList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.listAccessRequests.mockResolvedValue([pendingRequest]);
  });

  it('lists pending requesters with their note', async () => {
    render(<AccessRequestList projectId="p1" onChanged={vi.fn()} />);

    expect(await screen.findByText('Bob')).toBeInTheDocument();
    expect(screen.getByText('bob@corp')).toBeInTheDocument();
    expect(screen.getByText('joining the QBR team')).toBeInTheDocument();
  });

  it('defaults the role select to viewer', async () => {
    render(<AccessRequestList projectId="p1" onChanged={vi.fn()} />);

    const select = (await screen.findByLabelText('Role for Bob')) as HTMLSelectElement;
    expect(select.value).toBe('viewer');
  });

  it('approves with the selected role and notifies the parent', async () => {
    const onChanged = vi.fn();
    mocked.approveRequest.mockResolvedValue({ ...pendingRequest, status: 'approved' });
    render(<AccessRequestList projectId="p1" onChanged={onChanged} />);

    fireEvent.change(await screen.findByLabelText('Role for Bob'), {
      target: { value: 'editor' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Approve Bob' }));

    await waitFor(() => expect(mocked.approveRequest).toHaveBeenCalledWith('p1', 'r1', 'editor'));
    expect(onChanged).toHaveBeenCalled();
  });

  it('denies a request', async () => {
    mocked.denyRequest.mockResolvedValue({ ...pendingRequest, status: 'denied' });
    render(<AccessRequestList projectId="p1" onChanged={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Deny Bob' }));

    await waitFor(() => expect(mocked.denyRequest).toHaveBeenCalledWith('p1', 'r1'));
  });

  it('says so when nothing is pending', async () => {
    mocked.listAccessRequests.mockResolvedValue([]);
    render(<AccessRequestList projectId="p1" onChanged={vi.fn()} />);

    expect(await screen.findByText('No pending requests.')).toBeInTheDocument();
  });
});

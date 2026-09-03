import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AdminDashboard } from './AdminDashboard';
import { adminApi } from '../services/api';
import { AdminSystemStats, AdminUserList, AdminUserStats } from '../types';

vi.mock('../services/api', () => ({
  adminApi: {
    getStats: vi.fn(),
    getUsers: vi.fn(),
  },
}));

const stats: AdminSystemStats = {
  users_total: 42,
  users_active_30d: 12,
  users_new_30d: 3,
  entries_total: 128,
  entries_archived: 8,
  entries_by_status: { NEW: 1, IN_PROGRESS: 2, READY: 120, COMPLETE: 4, ERROR: 1 },
  entries_by_source: { upload: 100, url: 28 },
  storage_bytes_total: 1024 ** 3 * 5,
  duration_seconds_total: 36000,
  words_total: 1234567,
  projects_total: 7,
  entries_missing_metrics: 0,
  entries_unassigned: 0,
};

const users: AdminUserList = { total: 0, users: [] };

const ada: AdminUserStats = {
  id: 'u1',
  email: 'ada@corp.com',
  display_name: 'Ada Lovelace',
  is_admin: true,
  is_system: false,
  created_at: '2026-01-01T00:00:00Z',
  last_login_at: '2026-08-19T09:00:00Z',
  entry_count: 12,
  storage_bytes: 1024 ** 3,
  duration_seconds: 7200,
  word_count: 45000,
  error_count: 1,
  project_count: 3,
};

const populated: AdminUserList = { total: 1, users: [ada] };

// axios.isAxiosError() only looks for the `isAxiosError` marker, so a plain
// object with a response is enough to exercise the status-specific branches.
const axiosErrorWithStatus = (status: number) =>
  Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    response: { status, data: {} },
  });

const mocked = vi.mocked(adminApi);

describe('AdminDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.getStats.mockResolvedValue(stats);
    mocked.getUsers.mockResolvedValue(users);
  });

  it('renders the headline totals', async () => {
    render(<AdminDashboard />);

    expect(await screen.findByText('42')).toBeInTheDocument();
    expect(screen.getByText('128')).toBeInTheDocument();
    expect(screen.getByText('5.0 GB')).toBeInTheDocument();
    expect(screen.getByText('10.0 h')).toBeInTheDocument();
    expect(screen.getByText('1,234,567')).toBeInTheDocument();
  });

  it('hides the caveat when every entry has metrics', async () => {
    render(<AdminDashboard />);

    await screen.findByText('42');
    expect(screen.queryByText(/lower bound/i)).not.toBeInTheDocument();
  });

  it('warns when metrics are incomplete', async () => {
    mocked.getStats.mockResolvedValue({ ...stats, entries_missing_metrics: 9 });
    render(<AdminDashboard />);

    expect(await screen.findByText(/lower bound/i)).toBeInTheDocument();
    expect(screen.getByText(/9 entries/i)).toBeInTheDocument();
  });

  it('says nothing about unowned entries when there are none', async () => {
    render(<AdminDashboard />);

    await screen.findByText('42');
    expect(screen.queryByText(/no owner/i)).not.toBeInTheDocument();
  });

  it('flags entries that belong to no user', async () => {
    mocked.getStats.mockResolvedValue({ ...stats, entries_unassigned: 4 });
    render(<AdminDashboard />);

    expect(await screen.findByText(/no owner/i)).toBeInTheDocument();
    expect(screen.getByText(/4 entries have no owner/i)).toBeInTheDocument();
  });

  it('requests the first page sorted by storage descending', async () => {
    render(<AdminDashboard />);

    await screen.findByText('42');
    expect(mocked.getUsers).toHaveBeenCalledWith(0, 50, 'storage_bytes', 'desc');
  });

  it('refetches with the new sort key when another column is clicked', async () => {
    mocked.getUsers.mockResolvedValue(populated);
    render(<AdminDashboard />);
    await screen.findByText('42');

    fireEvent.click(screen.getByRole('button', { name: /entries/i }));

    await waitFor(() => expect(mocked.getUsers).toHaveBeenCalledWith(0, 50, 'entry_count', 'desc'));
  });

  it('refetches with a flipped order when the active column is clicked', async () => {
    mocked.getUsers.mockResolvedValue(populated);
    render(<AdminDashboard />);
    await screen.findByText('42');

    fireEvent.click(screen.getByRole('button', { name: /storage/i }));

    await waitFor(() =>
      expect(mocked.getUsers).toHaveBeenCalledWith(0, 50, 'storage_bytes', 'asc'),
    );
  });

  it('discards a stale response that lands after a newer one', async () => {
    const stale: AdminUserList = { total: 1, users: [{ ...ada, display_name: 'Stale Row' }] };
    const fresh: AdminUserList = { total: 1, users: [{ ...ada, display_name: 'Fresh Row' }] };
    let releaseStale: ((value: AdminUserList) => void) | undefined;

    mocked.getUsers.mockResolvedValueOnce(populated);
    render(<AdminDashboard />);
    await screen.findByText('42');

    // Second sort: left in flight so the third can overtake it.
    mocked.getUsers.mockImplementationOnce(
      () =>
        new Promise<AdminUserList>((resolve) => {
          releaseStale = resolve;
        }),
    );
    fireEvent.click(screen.getByRole('button', { name: /entries/i }));
    await waitFor(() => expect(releaseStale).toBeDefined());

    mocked.getUsers.mockResolvedValueOnce(fresh);
    fireEvent.click(screen.getByRole('button', { name: /words/i }));
    expect(await screen.findByText('Fresh Row')).toBeInTheDocument();

    releaseStale?.(stale);
    await waitFor(() => expect(mocked.getUsers).toHaveBeenCalledTimes(3));
    expect(screen.queryByText('Stale Row')).not.toBeInTheDocument();
    expect(screen.getByText('Fresh Row')).toBeInTheDocument();
  });

  it('shows an error state when the API rejects', async () => {
    mocked.getStats.mockRejectedValue(new Error('nope'));
    render(<AdminDashboard />);

    await waitFor(() =>
      expect(screen.getByText(/could not load admin statistics/i)).toBeInTheDocument(),
    );
  });

  it('reports a per-user failure without blaming the statistics', async () => {
    mocked.getUsers.mockRejectedValue(new Error('nope'));
    render(<AdminDashboard />);

    expect(await screen.findByText('42')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/could not load the per-user breakdown/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/could not load admin statistics/i)).not.toBeInTheDocument();
  });

  it('keeps the already-rendered cards when a refetch fails', async () => {
    mocked.getUsers.mockResolvedValue(populated);
    render(<AdminDashboard />);
    await screen.findByText('42');

    mocked.getStats.mockRejectedValue(new Error('nope'));
    mocked.getUsers.mockRejectedValue(new Error('nope'));
    fireEvent.click(screen.getByRole('button', { name: /entries/i }));

    await waitFor(() =>
      expect(screen.getByText(/could not load admin statistics/i)).toBeInTheDocument(),
    );
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('5.0 GB')).toBeInTheDocument();
  });

  it('renders a distinct not-found state when the admin gate answers 404', async () => {
    mocked.getStats.mockRejectedValue(axiosErrorWithStatus(404));
    mocked.getUsers.mockRejectedValue(axiosErrorWithStatus(404));
    render(<AdminDashboard />);

    expect(await screen.findByText(/not found/i)).toBeInTheDocument();
    expect(screen.queryByText(/could not load admin statistics/i)).not.toBeInTheDocument();
  });

  it('treats a non-404 failure as an error rather than a missing page', async () => {
    mocked.getStats.mockRejectedValue(axiosErrorWithStatus(500));
    mocked.getUsers.mockRejectedValue(axiosErrorWithStatus(500));
    render(<AdminDashboard />);

    await waitFor(() =>
      expect(screen.getByText(/could not load admin statistics/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/not found/i)).not.toBeInTheDocument();
  });
});

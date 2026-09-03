import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { AdminUserTable } from './AdminUserTable';
import { AdminUserStats } from '../types';

const user: AdminUserStats = {
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

describe('AdminUserTable', () => {
  it('renders a formatted row per user', () => {
    render(
      <AdminUserTable users={[user]} sort="storage_bytes" order="desc" onSortChange={vi.fn()} />,
    );

    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
    expect(screen.getByText('ada@corp.com')).toBeInTheDocument();
    expect(screen.getByText('1.0 GB')).toBeInTheDocument();
    expect(screen.getByText('2.0 h')).toBeInTheDocument();
    expect(screen.getByText('45,000')).toBeInTheDocument();
  });

  it('marks admins', () => {
    render(
      <AdminUserTable users={[user]} sort="storage_bytes" order="desc" onSortChange={vi.fn()} />,
    );

    expect(screen.getByText('admin')).toBeInTheDocument();
  });

  it('marks the synthetic system account', () => {
    render(
      <AdminUserTable
        users={[{ ...user, is_admin: false, is_system: true }]}
        sort="storage_bytes"
        order="desc"
        onSortChange={vi.fn()}
      />,
    );

    expect(screen.getByText('system')).toBeInTheDocument();
  });

  it('requests a new sort field on header click', () => {
    const onSortChange = vi.fn();
    render(
      <AdminUserTable
        users={[user]}
        sort="storage_bytes"
        order="desc"
        onSortChange={onSortChange}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /entries/i }));

    expect(onSortChange).toHaveBeenCalledWith('entry_count', 'desc');
  });

  it('flips the order when the active column is clicked again', () => {
    const onSortChange = vi.fn();
    render(
      <AdminUserTable
        users={[user]}
        sort="storage_bytes"
        order="desc"
        onSortChange={onSortChange}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /storage/i }));

    expect(onSortChange).toHaveBeenCalledWith('storage_bytes', 'asc');
  });

  it('exposes the active sort to assistive tech', () => {
    render(
      <AdminUserTable users={[user]} sort="storage_bytes" order="desc" onSortChange={vi.fn()} />,
    );

    const [storageHeader] = screen
      .getAllByRole('columnheader')
      .filter((header) => header.textContent?.match(/storage/i));

    expect(storageHeader).toHaveAttribute('aria-sort', 'descending');
    expect(screen.getByRole('button', { name: /storage/i })).toHaveAccessibleName(
      /sorted descending/i,
    );
    expect(screen.getByRole('button', { name: /entries/i })).toHaveAccessibleName(/^sort by/i);
  });

  it('reports an ascending sort as ascending', () => {
    render(<AdminUserTable users={[user]} sort="email" order="asc" onSortChange={vi.fn()} />);

    const [userHeader] = screen
      .getAllByRole('columnheader')
      .filter((header) => header.textContent?.match(/user/i));

    expect(userHeader).toHaveAttribute('aria-sort', 'ascending');
  });

  it('falls back to a placeholder for an unparseable join date', () => {
    render(
      <AdminUserTable
        users={[{ ...user, created_at: 'not-a-date' }]}
        sort="storage_bytes"
        order="desc"
        onSortChange={vi.fn()}
      />,
    );

    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('renders an empty state', () => {
    render(<AdminUserTable users={[]} sort="storage_bytes" order="desc" onSortChange={vi.fn()} />);

    expect(screen.getByText('No users yet.')).toBeInTheDocument();
  });
});

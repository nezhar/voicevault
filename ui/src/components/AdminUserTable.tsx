import React from 'react';
import { AdminUserSort, AdminUserStats } from '../types';
import { formatBytes, formatCount, formatHours } from '../utils/format';

interface AdminUserTableProps {
  users: AdminUserStats[];
  sort: AdminUserSort;
  order: 'asc' | 'desc';
  onSortChange: (sort: AdminUserSort, order: 'asc' | 'desc') => void;
}

const COLUMNS: { key: AdminUserSort; label: string; numeric: boolean }[] = [
  { key: 'email', label: 'User', numeric: false },
  { key: 'entry_count', label: 'Entries', numeric: true },
  { key: 'storage_bytes', label: 'Storage', numeric: true },
  { key: 'duration_seconds', label: 'Material', numeric: true },
  { key: 'word_count', label: 'Words', numeric: true },
  { key: 'created_at', label: 'Joined', numeric: false },
];

const formatDate = (value: string | null): string => {
  if (!value) {
    return '—';
  }
  // An unparseable timestamp makes toISOString() throw, which would take the
  // whole table down; show the same placeholder as a missing one.
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toISOString().slice(0, 10);
};

export const AdminUserTable: React.FC<AdminUserTableProps> = ({
  users,
  sort,
  order,
  onSortChange,
}) => {
  // Clicking the active column flips direction; a new column starts descending,
  // which is what you want for "who is consuming the most".
  const handleSort = (key: AdminUserSort) =>
    onSortChange(key, key === sort && order === 'desc' ? 'asc' : 'desc');

  if (users.length === 0) {
    return <p className="py-8 text-center text-sm text-gray-500">No users yet.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            {COLUMNS.map((column) => {
              const isActive = sort === column.key;
              const direction = order === 'desc' ? 'descending' : 'ascending';
              const nextDirection = order === 'desc' ? 'ascending' : 'descending';

              return (
                <th
                  key={column.key}
                  scope="col"
                  aria-sort={isActive ? direction : 'none'}
                  className={`px-4 py-3 ${column.numeric ? 'text-right' : 'text-left'}`}
                >
                  <button
                    onClick={() => handleSort(column.key)}
                    className="text-xs font-semibold uppercase tracking-wide text-gray-500 hover:text-gray-900"
                    // The arrow is decorative, so the direction has to be spelled
                    // out for anyone who cannot see it.
                    aria-label={
                      isActive
                        ? `${column.label}, sorted ${direction}. Activate to sort ${nextDirection}.`
                        : `Sort by ${column.label}`
                    }
                  >
                    {column.label}
                    {isActive && (order === 'desc' ? ' ↓' : ' ↑')}
                  </button>
                </th>
              );
            })}
            <th
              scope="col"
              className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500"
            >
              Errors
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {users.map((user) => (
            <tr key={user.id} className="hover:bg-gray-50">
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-900">{user.display_name}</span>
                  {user.is_admin && (
                    <span className="rounded bg-primary-50 px-1.5 py-0.5 text-[10px] uppercase text-primary-700">
                      admin
                    </span>
                  )}
                  {user.is_system && (
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] uppercase text-gray-500">
                      system
                    </span>
                  )}
                </div>
                <div className="text-xs text-gray-500">{user.email}</div>
              </td>
              <td className="px-4 py-3 text-right text-gray-700">
                {formatCount(user.entry_count)}
              </td>
              <td className="px-4 py-3 text-right text-gray-700">
                {formatBytes(user.storage_bytes)}
              </td>
              <td className="px-4 py-3 text-right text-gray-700">
                {formatHours(user.duration_seconds)}
              </td>
              <td className="px-4 py-3 text-right text-gray-700">{formatCount(user.word_count)}</td>
              <td className="px-4 py-3 text-gray-500">{formatDate(user.created_at)}</td>
              <td className="px-4 py-3 text-right text-gray-500">
                {formatCount(user.error_count)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

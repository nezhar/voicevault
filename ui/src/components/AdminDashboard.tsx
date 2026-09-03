import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { AlertTriangle, FileText, FolderOpen, HardDrive, Timer, Type, Users } from 'lucide-react';
import { adminApi } from '../services/api';
import { AdminSystemStats, AdminUserList, AdminUserSort } from '../types';
import { formatBytes, formatCount, formatHours } from '../utils/format';
import { AdminUserTable } from './AdminUserTable';

const PAGE_SIZE = 50;

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
}

const errorFrom = (err: unknown, fallback: string): string => {
  const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
  return detail || fallback;
};

// The admin endpoints answer 404 (not 403) for a non-admin, so a direct visit to
// /admin has to read as "there is nothing here", not as a backend failure.
const isNotFound = (err: unknown): boolean =>
  axios.isAxiosError(err) && err.response?.status === 404;

const StatCard: React.FC<StatCardProps> = ({ icon, label, value, hint }) => (
  <div className="rounded-lg border border-gray-200 bg-white p-4">
    <div className="flex items-center gap-2 text-gray-500">
      {icon}
      <span className="text-xs font-semibold uppercase tracking-wide">{label}</span>
    </div>
    <div className="mt-2 text-2xl font-bold text-gray-900">{value}</div>
    {hint && <div className="mt-1 text-xs text-gray-500">{hint}</div>}
  </div>
);

export const AdminDashboard: React.FC = () => {
  const [stats, setStats] = useState<AdminSystemStats | null>(null);
  const [userList, setUserList] = useState<AdminUserList | null>(null);
  const [sort, setSort] = useState<AdminUserSort>('storage_bytes');
  const [order, setOrder] = useState<'asc' | 'desc'>('desc');
  const [statsError, setStatsError] = useState<string | null>(null);
  const [usersError, setUsersError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  // `isStale` lets a superseded request (two quick header clicks) drop its
  // result instead of overwriting the newer one.
  const load = useCallback(
    async (isStale: () => boolean) => {
      // allSettled so one failing call cannot hide the other's good data.
      const [statsResult, usersResult] = await Promise.allSettled([
        adminApi.getStats(),
        adminApi.getUsers(0, PAGE_SIZE, sort, order),
      ]);

      if (isStale()) {
        return;
      }

      const reasons = [statsResult, usersResult]
        .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
        .map((result) => result.reason);

      if (reasons.some(isNotFound)) {
        setNotFound(true);
        return;
      }
      setNotFound(false);

      if (statsResult.status === 'fulfilled') {
        setStats(statsResult.value);
        setStatsError(null);
      } else {
        setStatsError(errorFrom(statsResult.reason, 'Could not load admin statistics.'));
      }

      if (usersResult.status === 'fulfilled') {
        setUserList(usersResult.value);
        setUsersError(null);
      } else {
        setUsersError(errorFrom(usersResult.reason, 'Could not load the per-user breakdown.'));
      }
    },
    [sort, order],
  );

  useEffect(() => {
    let ignore = false;
    load(() => ignore);
    return () => {
      ignore = true;
    };
  }, [load]);

  const handleSortChange = (nextSort: AdminUserSort, nextOrder: 'asc' | 'desc') => {
    setSort(nextSort);
    setOrder(nextOrder);
  };

  if (notFound) {
    return (
      <div className="py-12 text-center">
        <h2 className="text-lg font-semibold text-gray-900">Not found</h2>
        <p className="mt-1 text-sm text-gray-500">This area is not available.</p>
      </div>
    );
  }

  // Only blank the view when there is genuinely nothing to show; a failed
  // refetch keeps the last good cards and reports itself inline instead.
  if (!stats) {
    if (statsError) {
      return (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {statsError}
        </div>
      );
    }
    return <div className="py-12 text-center text-sm text-gray-500">Loading…</div>;
  }

  // Both caveats say the same kind of thing — a headline number is not quite
  // what it looks like — so they share the one amber banner treatment instead
  // of each growing its own.
  const caveats: { key: string; body: React.ReactNode }[] = [];

  if (stats.entries_missing_metrics > 0) {
    caveats.push({
      key: 'missing-metrics',
      body: (
        <>
          These totals are a lower bound: {formatCount(stats.entries_missing_metrics)} entries have
          no recorded metrics yet. Run{' '}
          <code className="rounded bg-amber-100 px-1">
            python -m app.scripts.backfill_entry_metrics
          </code>{' '}
          in the API container to fill them in.
        </>
      ),
    });
  }

  if (stats.entries_unassigned > 0) {
    caveats.push({
      key: 'unassigned',
      body: (
        <>
          {formatCount(stats.entries_unassigned)} entries have no owner. They are counted in the
          totals above, but they appear in no user&rsquo;s row below, so the per-user figures will
          not add up to the system ones.
        </>
      ),
    });
  }

  return (
    <div className="space-y-8">
      {[statsError, usersError]
        .filter((message): message is string => Boolean(message))
        .map((message) => (
          <div
            key={message}
            className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
          >
            {message}
          </div>
        ))}

      <div>
        <h2 className="text-lg font-semibold text-gray-900">System</h2>
        <p className="text-sm text-gray-500">Platform-wide consumption at a glance.</p>
      </div>

      {caveats.length > 0 && (
        <div className="space-y-3">
          {caveats.map(({ key, body }) => (
            <div
              key={key}
              className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{body}</span>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          icon={<Users className="h-4 w-4" />}
          label="Users"
          value={formatCount(stats.users_total)}
          hint={`${formatCount(stats.users_active_30d)} active · ${formatCount(stats.users_new_30d)} new (30d)`}
        />
        <StatCard
          icon={<FileText className="h-4 w-4" />}
          label="Files"
          value={formatCount(stats.entries_total)}
          hint={`${formatCount(stats.entries_by_source.upload ?? 0)} uploaded · ${formatCount(stats.entries_by_source.url ?? 0)} from URL · ${formatCount(stats.entries_archived)} archived`}
        />
        <StatCard
          icon={<HardDrive className="h-4 w-4" />}
          label="Storage"
          value={formatBytes(stats.storage_bytes_total)}
        />
        <StatCard
          icon={<Timer className="h-4 w-4" />}
          label="Material"
          value={formatHours(stats.duration_seconds_total)}
        />
        <StatCard
          icon={<Type className="h-4 w-4" />}
          label="Words transcribed"
          value={formatCount(stats.words_total)}
        />
        <StatCard
          icon={<FolderOpen className="h-4 w-4" />}
          label="Projects"
          value={formatCount(stats.projects_total)}
          hint={`${formatCount(stats.entries_by_status.ERROR ?? 0)} entries in error`}
        />
      </div>

      <div>
        <h2 className="text-lg font-semibold text-gray-900">Per user</h2>
        <p className="text-sm text-gray-500">
          Showing {formatCount(userList?.users.length ?? 0)} of {formatCount(userList?.total ?? 0)}.
        </p>
      </div>

      <AdminUserTable
        users={userList?.users ?? []}
        sort={sort}
        order={order}
        onSortChange={handleSortChange}
      />
    </div>
  );
};

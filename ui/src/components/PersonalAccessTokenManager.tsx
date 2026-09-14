import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { KeyRound, Pencil, X } from 'lucide-react';

import { adminApi, authApi } from '../services/api';
import {
  PATPermission,
  PATStatus,
  PATUser,
  PersonalAccessToken,
  PersonalAccessTokenUpdate,
  User,
} from '../types';
import { errorFrom } from '../utils/errors';
import { formatDateTime, formatRelative, parseApiDate } from '../utils/format';
import { statusOf } from '../utils/tokens';
import { ConfirmDialog } from './ConfirmDialog';
import { CopyButton } from './CopyButton';
import { IntegrationGuide } from './IntegrationGuide';
import { SegmentedControl } from './SegmentedControl';

type StatusFilter = PATStatus | 'all';
type Scope = 'mine' | 'all';
type TokenRow = PersonalAccessToken & { user?: PATUser };

const PAGE_SIZE = 25;
const EXPIRING_SOON_MS = 7 * 24 * 3600 * 1000;

const PERMISSIONS: { value: PATPermission; label: string; hint: string; adminOnly?: boolean }[] = [
  { value: 'entries:read', label: 'Read entries', hint: 'List entries, read transcripts, chat' },
  { value: 'entries:write', label: 'Write entries', hint: 'Upload, edit, archive, delete' },
  { value: 'projects:read', label: 'Read projects', hint: 'List and view projects' },
  { value: 'projects:write', label: 'Write projects', hint: 'Create projects, manage members' },
  { value: 'templates:read', label: 'Read templates', hint: 'List prompt templates' },
  { value: 'templates:write', label: 'Write templates', hint: 'Create, edit, delete templates' },
  { value: 'admin:read', label: 'Read admin data', hint: 'Platform statistics', adminOnly: true },
];

const EXPIRY_PRESETS: { label: string; days: number | null }[] = [
  { label: '30 days', days: 30 },
  { label: '90 days', days: 90 },
  { label: '1 year', days: 365 },
  { label: 'Never', days: null },
];

const STATUS_BADGE: Record<PATStatus, { label: string; className: string; dot: string }> = {
  active: {
    label: 'Active',
    className: 'bg-green-50 text-green-800 ring-green-600/20',
    dot: 'bg-green-500',
  },
  expired: {
    label: 'Expired',
    className: 'bg-gray-100 text-gray-700 ring-gray-500/20',
    dot: 'bg-gray-400',
  },
  revoked: {
    label: 'Revoked',
    className: 'bg-red-50 text-red-800 ring-red-600/20',
    dot: 'bg-red-500',
  },
};

// <input type="datetime-local"> wants local wall-clock time without a zone.
const toLocalInputValue = (date: Date): string => {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

const presetValue = (days: number | null): string => {
  if (days === null) return '';
  const date = new Date();
  date.setDate(date.getDate() + days);
  return toLocalInputValue(date);
};

// Local input value -> API value. '' means "never expires".
const toApiExpiry = (value: string): string | null =>
  value ? new Date(value).toISOString() : null;

function ExpiryPresets({ onPick }: { onPick: (days: number | null) => void }) {
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5" aria-label="Expiry presets">
      {EXPIRY_PRESETS.map((preset) => (
        <button
          key={preset.label}
          type="button"
          onClick={() => onPick(preset.days)}
          className="rounded-full border px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-50"
        >
          {preset.label}
        </button>
      ))}
    </div>
  );
}

interface EditState {
  name: string;
  expiresAt: string;
}

function TokenRowEditor({
  pat,
  busy,
  onSave,
  onCancel,
}: {
  pat: PersonalAccessToken;
  busy: boolean;
  onSave: (changes: PersonalAccessTokenUpdate) => void;
  onCancel: () => void;
}) {
  const initialExpiry = pat.expires_at ? toLocalInputValue(parseApiDate(pat.expires_at)) : '';
  const [draft, setDraft] = useState<EditState>({ name: pat.name, expiresAt: initialExpiry });
  const changes: PersonalAccessTokenUpdate = {};
  if (draft.name.trim() !== pat.name) changes.name = draft.name.trim();
  // Compare in the representation the field actually edits. Comparing the
  // outbound ISO string against the API's own would differ for every token that
  // has an expiry - the input is minute-precision local time, the API sends
  // sub-second UTC - so Save would light up on an untouched form and a plain
  // rename would silently rewrite the expiry.
  if (draft.expiresAt !== initialExpiry) changes.expires_at = toApiExpiry(draft.expiresAt);
  const dirty = Object.keys(changes).length > 0;

  return (
    <form
      className="w-full space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (dirty) onSave(changes);
      }}
      aria-label={`Edit ${pat.name}`}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm text-gray-700">
          Name
          <input
            required
            maxLength={100}
            value={draft.name}
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
            className="mt-1 w-full rounded border px-3 py-2"
          />
        </label>
        <div className="text-sm text-gray-700">
          <label>
            Expires
            <input
              type="datetime-local"
              value={draft.expiresAt}
              onChange={(event) => setDraft({ ...draft, expiresAt: event.target.value })}
              className="mt-1 w-full rounded border px-3 py-2"
            />
          </label>
          <ExpiryPresets onPick={(days) => setDraft({ ...draft, expiresAt: presetValue(days) })} />
        </div>
      </div>
      <p className="text-xs text-gray-500">
        Permissions cannot be changed. Create a new token if you need a different scope.
      </p>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="rounded border px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={busy || !dirty || !draft.name.trim()}
          className="rounded bg-primary-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? 'Saving…' : 'Save'}
        </button>
      </div>
    </form>
  );
}

function StatusBadge({ status }: { status: PATStatus }) {
  const badge = STATUS_BADGE[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${badge.className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} aria-hidden="true" />
      {badge.label}
    </span>
  );
}

interface Props {
  currentUser: User;
  isAdmin: boolean;
  /** Whether /mcp is enabled on this server; drives the MCP part of the guide. */
  mcpEnabled?: boolean;
}

export function PersonalAccessTokenManager({ currentUser, isAdmin, mcpEnabled = false }: Props) {
  // --- create form ---
  const [name, setName] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [permissions, setPermissions] = useState<PATPermission[]>([]);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<{ name: string; token: string } | null>(null);

  // --- per-row actions ---
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [revoking, setRevoking] = useState<TokenRow | null>(null);
  const [revokeBusy, setRevokeBusy] = useState(false);

  // --- token list ---
  const [tokens, setTokens] = useState<TokenRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('active');
  const [nameFilter, setNameFilter] = useState('');
  const [debouncedName, setDebouncedName] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  // A monotonic id rather than a per-effect flag: a write refetches by calling
  // refresh() straight away, and that call has to be ordered against the
  // effect-driven ones too, not only against other writes.
  const requestId = useRef(0);

  // --- admin-only scope ---
  const [scope, setScope] = useState<Scope>('mine');
  const [userFilter, setUserFilter] = useState<PATUser | null>(null);
  const [userSearch, setUserSearch] = useState('');
  const [userResults, setUserResults] = useState<PATUser[]>([]);
  const [userSearchLoading, setUserSearchLoading] = useState(false);

  const visiblePermissions = PERMISSIONS.filter((p) => isAdmin || !p.adminOnly);

  // `isStale` lets a superseded request drop its result instead of overwriting a
  // newer one - the filters, the scope and the heading all move together, so a
  // late response would otherwise show one user's rows under another's title.
  const load = useCallback(
    async (isStale: () => boolean) => {
      setLoading(true);
      try {
        if (isAdmin) {
          const result = await adminApi.getPATs({
            userId: scope === 'mine' ? currentUser.id : (userFilter?.id ?? undefined),
            name: debouncedName || undefined,
            status: statusFilter === 'all' ? undefined : statusFilter,
            page,
            perPage: PAGE_SIZE,
          });
          if (isStale()) return;
          setTokens(result.tokens);
          setTotal(result.total);
          setTotalPages(result.total_pages);
        } else {
          const rows = await authApi.listPATs();
          if (isStale()) return;
          setTokens(rows);
        }
        setError(null);
      } catch (err) {
        if (isStale()) return;
        setError(errorFrom(err, 'Could not load tokens.'));
      } finally {
        // The newer request owns the spinner; a stale one must not clear it.
        if (!isStale()) setLoading(false);
      }
    },
    [isAdmin, currentUser.id, scope, userFilter?.id, debouncedName, statusFilter, page],
  );

  const refresh = useCallback(() => {
    const id = (requestId.current += 1);
    return load(() => id !== requestId.current);
  }, [load]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedName(nameFilter.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [nameFilter]);

  useEffect(() => {
    if (!isAdmin || scope !== 'all') return;
    const query = userSearch.trim();
    if (query.length < 2) {
      setUserResults([]);
      setUserSearchLoading(false);
      return;
    }
    let cancelled = false;
    setUserSearchLoading(true);
    const timer = window.setTimeout(() => {
      adminApi
        .getPATUsers(query)
        .then((results) => {
          if (!cancelled) setUserResults(results);
        })
        .catch((err) => {
          if (!cancelled) setError(errorFrom(err, 'User search failed.'));
        })
        .finally(() => {
          if (!cancelled) setUserSearchLoading(false);
        });
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [isAdmin, scope, userSearch]);

  // Non-admins get every own token from the API and filter locally; admins are
  // filtered server-side, so this is a pass-through for them.
  const visibleTokens = useMemo(() => {
    if (isAdmin) return tokens;
    const needle = debouncedName.toLowerCase();
    return tokens.filter(
      (pat) =>
        (statusFilter === 'all' || statusOf(pat) === statusFilter) &&
        (!needle || pat.name.toLowerCase().includes(needle)),
    );
  }, [isAdmin, tokens, statusFilter, debouncedName]);

  const shownTotal = isAdmin ? total : visibleTokens.length;
  const filtersActive = statusFilter !== 'all' || debouncedName !== '';

  const resetPage = () => setPage(1);

  const togglePermission = (permission: PATPermission) =>
    setPermissions((current) =>
      current.includes(permission)
        ? current.filter((item) => item !== permission)
        : [...current, permission],
    );

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      // Tokens are always minted for the signed-in user.
      const result = await authApi.createPAT({
        name: name.trim(),
        permissions,
        expires_at: toApiExpiry(expiresAt),
      });
      setCreated({ name: result.name, token: result.token });
      setName('');
      setExpiresAt('');
      setPermissions([]);
      setError(null);
      if (isAdmin && scope !== 'mine') {
        setScope('mine');
        setUserFilter(null);
      }
      setStatusFilter('active');
      setPage(1);
      refresh();
    } catch (err) {
      setError(errorFrom(err, 'Could not create the token.'));
    } finally {
      setBusy(false);
    }
  };

  const confirmRevoke = async () => {
    if (!revoking) return;
    setRevokeBusy(true);
    try {
      await (isAdmin ? adminApi.revokePAT(revoking.id) : authApi.revokePAT(revoking.id));
      setRevoking(null);
      refresh();
    } catch (err) {
      setError(errorFrom(err, 'Could not revoke the token.'));
      setRevoking(null);
    } finally {
      setRevokeBusy(false);
    }
  };

  const saveEdit = async (pat: TokenRow, changes: PersonalAccessTokenUpdate) => {
    setSaving(true);
    try {
      const updated = await authApi.updatePAT(pat.id, changes);
      setTokens((current) =>
        current.map((row) => (row.id === pat.id ? { ...row, ...updated } : row)),
      );
      setEditingId(null);
      setError(null);
    } catch (err) {
      setError(errorFrom(err, 'Could not update the token.'));
    } finally {
      setSaving(false);
    }
  };

  const listTitle =
    !isAdmin || scope === 'mine'
      ? 'Your tokens'
      : userFilter
        ? `Tokens of ${userFilter.display_name}`
        : 'All tokens';

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold text-gray-900">
          <KeyRound className="h-5 w-5" /> Personal access tokens
        </h2>
        <p className="text-sm text-gray-500">
          Scoped credentials for scripts and API clients. Send one as{' '}
          <code className="rounded bg-gray-100 px-1 py-0.5 text-xs">Authorization: Bearer …</code>.
        </p>
      </div>

      {error && (
        <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* ---------------------------------------------------------------- create */}
      <section aria-labelledby="pat-create-heading" className="space-y-4">
        <h3 id="pat-create-heading" className="font-medium text-gray-900">
          Create a token
        </h3>

        {created && (
          <div
            role="status"
            className="space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-4"
          >
            <p className="font-medium text-amber-900">
              “{created.name}” is ready. Copy the token now — it will not be shown again.
            </p>
            <div className="flex gap-2">
              <code className="min-w-0 flex-1 overflow-x-auto rounded bg-white p-2 text-sm">
                {created.token}
              </code>
              <CopyButton text={created.token} label="Copy token" />
            </div>
            <div className="space-y-2">
              <p className="text-xs text-amber-900">Use it from a terminal or an MCP client:</p>
              <IntegrationGuide token={created.token} mcpEnabled={mcpEnabled} />
            </div>
            <button
              type="button"
              onClick={() => setCreated(null)}
              className="text-sm text-amber-800 underline"
            >
              I have saved it
            </button>
          </div>
        )}

        <form onSubmit={create} className="space-y-5 rounded-lg border bg-white p-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm text-gray-700">
              Name
              <input
                required
                maxLength={100}
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="mt-1 w-full rounded border px-3 py-2"
                placeholder="CI pipeline"
              />
              <span className="mt-1 block text-xs text-gray-500">
                Where the token will be used, so you recognise it later.
              </span>
            </label>
            <div className="text-sm text-gray-700">
              <label>
                Expires
                <input
                  type="datetime-local"
                  value={expiresAt}
                  onChange={(event) => setExpiresAt(event.target.value)}
                  className="mt-1 w-full rounded border px-3 py-2"
                />
              </label>
              <ExpiryPresets onPick={(days) => setExpiresAt(presetValue(days))} />
              {!expiresAt && (
                <span className="mt-1 block text-xs text-gray-500">
                  Never expires. Prefer a date for tokens you cannot rotate easily.
                </span>
              )}
            </div>
          </div>

          <fieldset>
            <legend className="mb-2 text-sm font-medium text-gray-700">Permissions</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {visiblePermissions.map(({ value, label, hint }) => (
                <label
                  key={value}
                  className="flex items-start gap-2 rounded border p-2 text-sm text-gray-700 has-[:checked]:border-primary-600 has-[:checked]:bg-primary-50"
                >
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={permissions.includes(value)}
                    onChange={() => togglePermission(value)}
                  />
                  <span>
                    <span className="block font-medium">{label}</span>
                    <span className="block text-xs text-gray-500">{hint}</span>
                  </span>
                </label>
              ))}
            </div>
            {permissions.length === 0 && (
              <p className="mt-2 text-xs text-gray-500">Select at least one permission.</p>
            )}
          </fieldset>

          <div className="flex items-center justify-between gap-4">
            <p className="text-xs text-gray-500">
              The token acts as <span className="font-medium">{currentUser.email}</span>.
            </p>
            <button
              disabled={busy || !name.trim() || permissions.length === 0}
              className="rounded bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {busy ? 'Creating…' : 'Create token'}
            </button>
          </div>
        </form>

        <details className="group rounded-lg border bg-white p-4">
          <summary className="cursor-pointer text-sm font-medium text-gray-900">
            How to use a token
            <span className="ml-2 text-xs font-normal text-gray-500">REST API and MCP</span>
          </summary>
          <div className="mt-3">
            <IntegrationGuide mcpEnabled={mcpEnabled} />
          </div>
        </details>
      </section>

      {/* ---------------------------------------------------------------- manage */}
      <section aria-labelledby="pat-list-heading" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 id="pat-list-heading" className="font-medium text-gray-900">
            {listTitle}
            <span className="ml-2 text-sm font-normal text-gray-500">({shownTotal})</span>
          </h3>
          {isAdmin && (
            <SegmentedControl
              label="Token scope"
              value={scope}
              options={[
                { value: 'mine', label: 'My tokens' },
                { value: 'all', label: 'All tokens' },
              ]}
              onChange={(next) => {
                setScope(next);
                setUserFilter(null);
                setUserSearch('');
                resetPage();
              }}
            />
          )}
        </div>

        <div className="space-y-3 rounded-lg border bg-white p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm text-gray-700">
              Status
              <select
                value={statusFilter}
                onChange={(event) => {
                  setStatusFilter(event.target.value as StatusFilter);
                  resetPage();
                }}
                className="mt-1 w-full rounded border px-3 py-2"
              >
                <option value="active">Active</option>
                <option value="expired">Expired</option>
                <option value="revoked">Revoked</option>
                <option value="all">All statuses</option>
              </select>
            </label>
            <label className="text-sm text-gray-700">
              Token name
              <input
                value={nameFilter}
                onChange={(event) => {
                  setNameFilter(event.target.value);
                  resetPage();
                }}
                className="mt-1 w-full rounded border px-3 py-2"
                placeholder="Filter by name"
              />
            </label>
          </div>

          {isAdmin && scope === 'all' && (
            <div className="text-sm text-gray-700">
              {userFilter ? (
                <div className="flex items-center gap-2">
                  <span>User:</span>
                  <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs">
                    {userFilter.display_name} · {userFilter.email}
                    {!userFilter.is_active && ' · inactive'}
                    <button
                      type="button"
                      aria-label="Clear user filter"
                      onClick={() => {
                        setUserFilter(null);
                        resetPage();
                      }}
                      className="rounded-full p-0.5 hover:bg-gray-200"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                </div>
              ) : (
                <label className="block">
                  Filter by user
                  <input
                    value={userSearch}
                    onChange={(event) => setUserSearch(event.target.value)}
                    className="mt-1 w-full rounded border px-3 py-2"
                    placeholder="Name or email, at least 2 characters"
                  />
                </label>
              )}
              {userSearchLoading && <p className="mt-1 text-xs text-gray-500">Searching…</p>}
              {!userFilter && userResults.length > 0 && (
                <div
                  className="mt-2 divide-y rounded border"
                  role="listbox"
                  aria-label="User results"
                >
                  {userResults.map((user) => (
                    <button
                      key={user.id}
                      type="button"
                      role="option"
                      aria-selected={false}
                      onClick={() => {
                        setUserFilter(user);
                        setUserSearch('');
                        setUserResults([]);
                        resetPage();
                      }}
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-gray-50"
                    >
                      <span>{user.display_name}</span>
                      <span className="text-gray-500">
                        {user.email}
                        {user.is_active ? '' : ' — inactive'}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {loading && tokens.length === 0 ? (
          <p className="text-sm text-gray-500">Loading tokens…</p>
        ) : visibleTokens.length === 0 ? (
          <div className="rounded-lg border border-dashed p-6 text-center text-sm text-gray-500">
            {filtersActive ? (
              <>
                <p>
                  No {statusFilter === 'all' ? '' : `${statusFilter} `}tokens
                  {debouncedName ? ` named “${debouncedName}”` : ''}.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setStatusFilter('all');
                    setNameFilter('');
                    resetPage();
                  }}
                  className="mt-2 text-primary-600 underline"
                >
                  Show all tokens
                </button>
              </>
            ) : (
              <p>No tokens yet. Create one above to get started.</p>
            )}
          </div>
        ) : (
          <ul className={`divide-y rounded-lg border bg-white ${loading ? 'opacity-60' : ''}`}>
            {visibleTokens.map((pat) => {
              const status = statusOf(pat);
              const expiresMs = pat.expires_at ? parseApiDate(pat.expires_at).getTime() : null;
              const expiringSoon =
                status === 'active' &&
                expiresMs !== null &&
                expiresMs - Date.now() < EXPIRING_SOON_MS;
              const isOwn = !pat.user || pat.user.id === currentUser.id;
              const editable = status === 'active' && isOwn;

              if (editingId === pat.id) {
                return (
                  <li key={pat.id} className="p-4">
                    <TokenRowEditor
                      pat={pat}
                      busy={saving}
                      onSave={(changes) => saveEdit(pat, changes)}
                      onCancel={() => setEditingId(null)}
                    />
                  </li>
                );
              }

              return (
                <li
                  key={pat.id}
                  className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between"
                >
                  <div className="min-w-0 space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-gray-900">{pat.name}</span>
                      <StatusBadge status={status} />
                    </div>
                    {isAdmin && pat.user && (
                      <div className="text-xs text-gray-500">
                        {pat.user.display_name} · {pat.user.email}
                        {isOwn && ' (you)'}
                      </div>
                    )}
                    <code className="block text-xs text-gray-500">{pat.token_prefix}…</code>
                    <div className="flex flex-wrap gap-1">
                      {pat.permissions.map((permission) => (
                        <span
                          key={permission}
                          className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[11px] text-gray-700"
                        >
                          {permission}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="flex shrink-0 flex-col gap-1 text-xs text-gray-500 sm:items-end sm:text-right">
                    <span className={expiringSoon ? 'font-medium text-amber-700' : undefined}>
                      {pat.expires_at
                        ? `${status === 'expired' ? 'Expired' : 'Expires'} ${formatDateTime(pat.expires_at)} (${formatRelative(pat.expires_at)})`
                        : 'Never expires'}
                    </span>
                    <span>
                      {pat.last_used_at
                        ? `Last used ${formatDateTime(pat.last_used_at)} (${formatRelative(pat.last_used_at)})`
                        : 'Never used'}
                    </span>
                    <span>Created {formatDateTime(pat.created_at)}</span>
                    {status === 'active' && (
                      <div className="mt-1 flex gap-3">
                        {editable && (
                          <button
                            type="button"
                            onClick={() => setEditingId(pat.id)}
                            className="flex items-center gap-1 text-sm text-gray-700 hover:underline"
                          >
                            <Pencil className="h-3.5 w-3.5" /> Edit
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => setRevoking(pat)}
                          className="text-sm text-red-600 hover:underline"
                        >
                          Revoke
                        </button>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {isAdmin && totalPages > 1 && (
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page <= 1 || loading}
              className="rounded border px-3 py-2 text-sm disabled:opacity-50"
            >
              Previous
            </button>
            <span className="text-sm text-gray-500">
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              disabled={page >= totalPages || loading}
              className="rounded border px-3 py-2 text-sm disabled:opacity-50"
            >
              Next
            </button>
          </div>
        )}
      </section>

      <ConfirmDialog
        open={revoking !== null}
        title={revoking ? `Revoke “${revoking.name}”?` : ''}
        description={
          revoking && (
            <>
              {revoking.user && revoking.user.id !== currentUser.id && (
                <p className="mb-1">
                  This token belongs to {revoking.user.display_name} ({revoking.user.email}).
                </p>
              )}
              <p>Clients using it will stop working immediately. This cannot be undone.</p>
            </>
          )
        }
        confirmLabel="Revoke token"
        busy={revokeBusy}
        onConfirm={confirmRevoke}
        onCancel={() => setRevoking(null)}
      />
    </div>
  );
}

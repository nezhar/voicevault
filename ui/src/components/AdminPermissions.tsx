import { useCallback, useEffect, useMemo, useState } from 'react';
import { X } from 'lucide-react';

import { adminApi } from '../services/api';
import { Capability, CapabilityInfo, EffectiveGrant, Grant, Group, PATUser } from '../types';
import { errorFrom } from '../utils/errors';

export type PermissionSubject =
  | { kind: 'user'; id: string; label: string }
  | { kind: 'group'; id: string; label: string };

interface Props {
  catalog: CapabilityInfo[];
  subject: PermissionSubject | null;
  onSubjectChange: (subject: PermissionSubject | null) => void;
  /** admin.manage: may change grants; otherwise the matrix is read-only. */
  canManage: boolean;
}

interface ProjectColumn {
  id: string;
  name: string;
}

const GLOBAL = '';
const key = (capability: Capability, projectId: string | null) =>
  `${capability}|${projectId ?? GLOBAL}`;

/**
 * The capability matrix of one user or group: rows are capabilities by area,
 * columns "Global" plus any projects. For a user, what their groups already
 * give is shown shaded with its source; only the user's own grants are edited.
 */
export function AdminPermissions({ catalog, subject, onSubjectChange, canManage }: Props) {
  const [groups, setGroups] = useState<Group[]>([]);
  const [userSearch, setUserSearch] = useState('');
  const [userResults, setUserResults] = useState<PATUser[]>([]);
  const [own, setOwn] = useState<Set<string>>(new Set());
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [inherited, setInherited] = useState<Map<string, string[]>>(new Map());
  const [userGroups, setUserGroups] = useState<string[]>([]);
  const [isAdminUser, setIsAdminUser] = useState(false);
  const [columns, setColumns] = useState<ProjectColumn[]>([]);
  const [projectSearch, setProjectSearch] = useState('');
  const [projectResults, setProjectResults] = useState<ProjectColumn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    adminApi
      .listGroups()
      .then(setGroups)
      .catch((err) => setError(errorFrom(err, 'Could not load groups.')));
  }, []);

  // user search
  useEffect(() => {
    const query = userSearch.trim();
    if (query.length < 2) {
      setUserResults([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      adminApi
        .getPATUsers(query)
        .then((results) => {
          if (!cancelled) setUserResults(results);
        })
        .catch(() => undefined);
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [userSearch]);

  // project search for new columns
  useEffect(() => {
    const query = projectSearch.trim();
    if (!query) {
      setProjectResults([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      adminApi
        .searchProjects(query)
        .then((results) => {
          if (!cancelled) setProjectResults(results);
        })
        .catch(() => undefined);
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [projectSearch]);

  const load = useCallback(async () => {
    if (!subject) return;
    setNotice(null);
    try {
      const params = subject.kind === 'user' ? { userId: subject.id } : { groupId: subject.id };
      const grants = await adminApi.getGrants(params);
      const ownKeys = new Set(grants.map((grant) => key(grant.capability, grant.project_id)));
      setOwn(ownKeys);
      setSaved(new Set(ownKeys));
      const projectColumns = new Map<string, string>();
      const addColumn = (grant: Grant) => {
        if (grant.project_id) {
          projectColumns.set(grant.project_id, grant.project_name ?? 'Unknown project');
        }
      };
      grants.forEach(addColumn);

      const inheritedMap = new Map<string, string[]>();
      if (subject.kind === 'user') {
        const permissions = await adminApi.getUserPermissions(subject.id);
        setIsAdminUser(permissions.is_admin);
        setUserGroups(permissions.groups);
        permissions.grants
          .filter((grant: EffectiveGrant) => grant.source !== 'user')
          .forEach((grant) => {
            addColumn(grant);
            const cell = key(grant.capability, grant.project_id);
            inheritedMap.set(cell, [...(inheritedMap.get(cell) ?? []), grant.source]);
          });
      } else {
        setIsAdminUser(false);
        setUserGroups([]);
      }
      setInherited(inheritedMap);
      setColumns(
        [...projectColumns.entries()]
          .map(([id, name]) => ({ id, name }))
          .sort((a, b) => a.name.localeCompare(b.name)),
      );
      setError(null);
    } catch (err) {
      setError(errorFrom(err, 'Could not load the permissions.'));
    }
  }, [subject]);

  useEffect(() => {
    load();
  }, [load]);

  const areas = useMemo(() => {
    const result: { area: string; items: CapabilityInfo[] }[] = [];
    catalog.forEach((item) => {
      const bucket = result.find((entry) => entry.area === item.area);
      if (bucket) bucket.items.push(item);
      else result.push({ area: item.area, items: [item] });
    });
    return result;
  }, [catalog]);

  const dirty = own.size !== saved.size || [...own].some((cell) => !saved.has(cell));

  const toggle = (cell: string) =>
    setOwn((current) => {
      const next = new Set(current);
      if (next.has(cell)) next.delete(cell);
      else next.add(cell);
      return next;
    });

  const save = async () => {
    if (!subject) return;
    setBusy(true);
    try {
      const grants: Grant[] = [...own].map((cell) => {
        const [capability, projectId] = cell.split('|');
        return { capability: capability as Capability, project_id: projectId || null };
      });
      const params = subject.kind === 'user' ? { userId: subject.id } : { groupId: subject.id };
      await adminApi.setGrants(params, grants);
      await load();
      setNotice('Permissions saved. They apply from the next request.');
    } catch (err) {
      setError(errorFrom(err, 'Could not save the permissions.'));
    } finally {
      setBusy(false);
    }
  };

  const addColumn = (project: ProjectColumn) => {
    setColumns((current) =>
      current.some((column) => column.id === project.id) ? current : [...current, project],
    );
    setProjectSearch('');
    setProjectResults([]);
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Permissions</h2>
        <p className="text-sm text-gray-500">
          Grants only add: a user may do what they, their groups or Everyone are granted, globally
          or in single projects. Which content they reach still depends on project membership.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-lg border bg-white p-4">
        <label className="text-sm text-gray-700">
          Group
          <select
            value={subject?.kind === 'group' ? subject.id : ''}
            onChange={(event) => {
              const group = groups.find((item) => item.id === event.target.value);
              onSubjectChange(group ? { kind: 'group', id: group.id, label: group.name } : null);
            }}
            className="mt-1 block rounded border px-3 py-2"
          >
            <option value="">Choose a group…</option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>
        </label>
        <span className="pb-2 text-sm text-gray-400">or</span>
        <div className="relative text-sm text-gray-700">
          <label>
            User
            <input
              value={userSearch}
              onChange={(event) => setUserSearch(event.target.value)}
              className="mt-1 block w-64 rounded border px-3 py-2"
              placeholder="Name or email, at least 2 characters"
            />
          </label>
          {userResults.length > 0 && (
            <div
              role="listbox"
              aria-label="User results"
              className="absolute z-10 mt-1 w-80 divide-y rounded border bg-white shadow"
            >
              {userResults.map((user) => (
                <button
                  key={user.id}
                  type="button"
                  role="option"
                  aria-selected={false}
                  onClick={() => {
                    onSubjectChange({ kind: 'user', id: user.id, label: user.display_name });
                    setUserSearch('');
                    setUserResults([]);
                  }}
                  className="block w-full px-3 py-2 text-left hover:bg-gray-50"
                >
                  {user.display_name}
                  <span className="ml-2 text-gray-500">{user.email}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {error && (
        <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}
      {notice && (
        <div role="status" className="rounded-lg bg-green-50 p-3 text-sm text-green-800">
          {notice}
        </div>
      )}

      {!subject ? (
        <div className="rounded-lg border border-dashed p-6 text-center text-sm text-gray-500">
          Choose a group or a user to see and change their capabilities.
        </div>
      ) : (
        <div className="space-y-3 rounded-lg border bg-white p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-medium text-gray-900">
                {subject.kind === 'group' ? 'Group' : 'User'}: {subject.label}
              </h3>
              {subject.kind === 'user' && (
                <p className="text-xs text-gray-500">
                  {isAdminUser
                    ? 'Administrator: holds every capability regardless of grants.'
                    : `Groups: ${userGroups.join(', ') || 'none'}. Shaded boxes come from a group.`}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => onSubjectChange(null)}
              aria-label="Close"
              className="rounded p-1 text-gray-500 hover:bg-gray-100"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {canManage && (
            <div className="relative text-sm text-gray-700">
              <label>
                Add a project column
                <input
                  value={projectSearch}
                  onChange={(event) => setProjectSearch(event.target.value)}
                  className="mt-1 block w-64 rounded border px-3 py-2"
                  placeholder="Project name"
                />
              </label>
              {projectResults.length > 0 && (
                <div
                  role="listbox"
                  aria-label="Project results"
                  className="absolute z-10 mt-1 w-64 divide-y rounded border bg-white shadow"
                >
                  {projectResults.map((project) => (
                    <button
                      key={project.id}
                      type="button"
                      role="option"
                      aria-selected={false}
                      onClick={() => addColumn(project)}
                      className="block w-full px-3 py-2 text-left hover:bg-gray-50"
                    >
                      {project.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-gray-500">
                  <th className="py-2 pr-4">Capability</th>
                  <th className="px-3 py-2 text-center">Global</th>
                  {columns.map((column) => (
                    <th key={column.id} className="px-3 py-2 text-center normal-case">
                      {column.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {areas.map(({ area, items }) => [
                  <tr key={`area-${area}`}>
                    <td
                      colSpan={2 + columns.length}
                      className="pt-3 text-xs font-semibold uppercase tracking-wide text-gray-400"
                    >
                      {area}
                    </td>
                  </tr>,
                  ...items.map((item) => (
                    <tr key={item.name} className="border-t">
                      <td className="py-2 pr-4">
                        <span className="block text-gray-900">{item.label}</span>
                        <span className="block font-mono text-[11px] text-gray-400">
                          {item.name}
                        </span>
                      </td>
                      {[null, ...columns.map((column) => column.id)].map((projectId) => {
                        const cell = key(item.name, projectId);
                        if (projectId && !item.project_scoped) {
                          return (
                            <td
                              key={cell}
                              className="px-3 py-2 text-center text-gray-300"
                              title="Global only"
                            >
                              —
                            </td>
                          );
                        }
                        const from = inherited.get(cell);
                        const checked = own.has(cell);
                        return (
                          <td
                            key={cell}
                            className={`px-3 py-2 text-center ${from ? 'bg-gray-50' : ''}`}
                            title={from ? `From ${from.join(', ')}` : undefined}
                          >
                            <input
                              type="checkbox"
                              aria-label={`${item.label} ${
                                projectId
                                  ? `in ${columns.find((c) => c.id === projectId)?.name}`
                                  : 'globally'
                              }`}
                              checked={checked || (!!from && !checked)}
                              ref={(element) => {
                                if (element) element.indeterminate = !!from && !checked;
                              }}
                              disabled={!canManage || busy}
                              onChange={() => toggle(cell)}
                            />
                          </td>
                        );
                      })}
                    </tr>
                  )),
                ])}
              </tbody>
            </table>
          </div>

          {canManage && (
            <div className="flex justify-end gap-2">
              <button
                type="button"
                disabled={!dirty || busy}
                onClick={() => load()}
                className="rounded border px-3 py-1.5 text-sm text-gray-700 disabled:opacity-50"
              >
                Reset
              </button>
              <button
                type="button"
                disabled={!dirty || busy}
                onClick={save}
                className="rounded bg-primary-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                {busy ? 'Saving…' : 'Save permissions'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

import { useCallback, useEffect, useState } from 'react';
import { Trash2, Users } from 'lucide-react';

import { adminApi } from '../services/api';
import { Group, GroupDetail } from '../types';
import { errorFrom } from '../utils/errors';
import { ConfirmDialog } from './ConfirmDialog';

interface Props {
  /** Open the permission editor for a group. */
  onEditPermissions?: (group: Group) => void;
}

const emptyForm = { name: '', description: '', idp_group: '' };

/** Admin: groups, their IdP link and their manual members. */
export function AdminGroups({ onEditPermissions }: Props) {
  const [groups, setGroups] = useState<Group[]>([]);
  const [selected, setSelected] = useState<GroupDetail | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [creating, setCreating] = useState(false);
  const [memberEmail, setMemberEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Group | null>(null);

  const loadGroups = useCallback(async () => {
    try {
      setGroups(await adminApi.listGroups());
    } catch (err) {
      setError(errorFrom(err, 'Could not load groups.'));
    }
  }, []);

  useEffect(() => {
    loadGroups();
  }, [loadGroups]);

  const open = async (group: Group) => {
    setCreating(false);
    try {
      const detail = await adminApi.getGroup(group.id);
      setSelected(detail);
      setForm({
        name: detail.name,
        description: detail.description ?? '',
        idp_group: detail.idp_group ?? '',
      });
      setError(null);
    } catch (err) {
      setError(errorFrom(err, 'Could not load the group.'));
    }
  };

  const startCreate = () => {
    setSelected(null);
    setCreating(true);
    setForm(emptyForm);
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      idp_group: form.idp_group.trim() || null,
    };
    try {
      const saved = creating
        ? await adminApi.createGroup(payload)
        : await adminApi.updateGroup(
            selected!.id,
            selected!.is_builtin ? { description: payload.description } : payload,
          );
      setSelected(saved);
      setCreating(false);
      setError(null);
      await loadGroups();
    } catch (err) {
      setError(errorFrom(err, 'Could not save the group.'));
    } finally {
      setBusy(false);
    }
  };

  const addMember = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    try {
      setSelected(await adminApi.addGroupMember(selected.id, memberEmail.trim()));
      setMemberEmail('');
      setError(null);
      await loadGroups();
    } catch (err) {
      setError(errorFrom(err, 'Could not add the member.'));
    } finally {
      setBusy(false);
    }
  };

  const removeMember = async (userId: string) => {
    if (!selected) return;
    setBusy(true);
    try {
      await adminApi.removeGroupMember(selected.id, userId);
      setSelected(await adminApi.getGroup(selected.id));
      await loadGroups();
    } catch (err) {
      setError(errorFrom(err, 'Could not remove the member.'));
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleting) return;
    setBusy(true);
    try {
      await adminApi.deleteGroup(deleting.id);
      if (selected?.id === deleting.id) setSelected(null);
      setDeleting(null);
      await loadGroups();
    } catch (err) {
      setError(errorFrom(err, 'Could not delete the group.'));
      setDeleting(null);
    } finally {
      setBusy(false);
    }
  };

  const editing = creating || selected !== null;
  const builtin = selected?.is_builtin ?? false;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Groups</h2>
          <p className="text-sm text-gray-500">
            Grant capabilities and share projects with many people at once. Link a group to an IdP
            group to keep its members in sync at every sign-in.
          </p>
        </div>
        <button
          type="button"
          onClick={startCreate}
          className="rounded bg-primary-600 px-3 py-2 text-sm font-medium text-white"
        >
          New group
        </button>
      </div>

      {error && (
        <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <ul className="divide-y rounded-lg border bg-white" aria-label="Groups">
          {groups.map((group) => (
            <li key={group.id}>
              <button
                type="button"
                onClick={() => open(group)}
                aria-current={selected?.id === group.id}
                className={`flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm hover:bg-gray-50 ${
                  selected?.id === group.id ? 'bg-primary-50' : ''
                }`}
              >
                <span className="min-w-0">
                  <span className="block font-medium text-gray-900">{group.name}</span>
                  <span className="block truncate text-xs text-gray-500">
                    {group.is_builtin
                      ? 'Every user · baseline for everybody'
                      : group.idp_group
                        ? `IdP group: ${group.idp_group}`
                        : 'Managed here'}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1 text-xs text-gray-500">
                  <Users className="h-3.5 w-3.5" />
                  {group.member_count ?? 'all'}
                </span>
              </button>
            </li>
          ))}
        </ul>

        {editing ? (
          <div className="space-y-4 rounded-lg border bg-white p-4">
            <form onSubmit={save} className="space-y-3" aria-label="Group settings">
              <label className="block text-sm text-gray-700">
                Name
                <input
                  required
                  maxLength={100}
                  disabled={builtin}
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                  className="mt-1 w-full rounded border px-3 py-2 disabled:bg-gray-50"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Description
                <input
                  maxLength={2000}
                  value={form.description}
                  onChange={(event) => setForm({ ...form, description: event.target.value })}
                  className="mt-1 w-full rounded border px-3 py-2"
                />
              </label>
              {!builtin && (
                <label className="block text-sm text-gray-700">
                  IdP group
                  <input
                    maxLength={255}
                    value={form.idp_group}
                    onChange={(event) => setForm({ ...form, idp_group: event.target.value })}
                    className="mt-1 w-full rounded border px-3 py-2"
                    placeholder="Name as sent in the groups claim (optional)"
                  />
                  <span className="mt-1 block text-xs text-gray-500">
                    Members are taken from the OIDC groups claim at each sign-in. Changing it drops
                    the members synced from the old IdP group.
                  </span>
                </label>
              )}
              <div className="flex flex-wrap justify-end gap-2">
                {selected && onEditPermissions && (
                  <button
                    type="button"
                    onClick={() => onEditPermissions(selected)}
                    className="rounded border px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
                  >
                    Permissions
                  </button>
                )}
                {selected && !builtin && (
                  <button
                    type="button"
                    onClick={() => setDeleting(selected)}
                    className="rounded border border-red-200 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50"
                  >
                    Delete
                  </button>
                )}
                <button
                  type="submit"
                  disabled={busy || !form.name.trim()}
                  className="rounded bg-primary-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                >
                  {creating ? 'Create group' : 'Save'}
                </button>
              </div>
            </form>

            {selected && !builtin && (
              <div className="space-y-3 border-t pt-4">
                <h3 className="text-sm font-medium text-gray-900">Members</h3>
                <form onSubmit={addMember} className="flex gap-2">
                  <input
                    type="email"
                    required
                    value={memberEmail}
                    onChange={(event) => setMemberEmail(event.target.value)}
                    className="min-w-0 flex-1 rounded border px-3 py-2 text-sm"
                    placeholder="Email of a user who has signed in"
                    aria-label="Member email"
                  />
                  <button
                    disabled={busy || !memberEmail.trim()}
                    className="rounded border px-3 py-2 text-sm disabled:opacity-50"
                  >
                    Add
                  </button>
                </form>
                {selected.members.length === 0 ? (
                  <p className="text-sm text-gray-500">No members yet.</p>
                ) : (
                  <ul className="divide-y rounded border">
                    {selected.members.map((member) => (
                      <li
                        key={`${member.user_id}-${member.source}`}
                        className="flex items-center justify-between gap-2 px-3 py-2 text-sm"
                      >
                        <span className="min-w-0">
                          <span className="block text-gray-900">{member.display_name}</span>
                          <span className="block truncate text-xs text-gray-500">
                            {member.email}
                          </span>
                        </span>
                        {member.source === 'idp' ? (
                          <span
                            className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600"
                            title="Synced from the IdP at sign-in"
                          >
                            IdP
                          </span>
                        ) : (
                          <button
                            type="button"
                            onClick={() => removeMember(member.user_id)}
                            disabled={busy}
                            aria-label={`Remove ${member.email}`}
                            className="rounded p-1 text-gray-500 hover:bg-gray-100 hover:text-red-600"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            {builtin && (
              <p className="border-t pt-4 text-sm text-gray-500">
                Everyone contains every user. Its capabilities are the baseline that every other
                grant adds to.
              </p>
            )}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed p-6 text-center text-sm text-gray-500">
            Select a group, or create a new one.
          </div>
        )}
      </div>

      <ConfirmDialog
        open={deleting !== null}
        title={deleting ? `Delete “${deleting.name}”?` : ''}
        description={
          <p>
            Its members lose the capabilities and project access the group gave them. This cannot be
            undone.
          </p>
        }
        confirmLabel="Delete group"
        busy={busy}
        onConfirm={confirmDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}

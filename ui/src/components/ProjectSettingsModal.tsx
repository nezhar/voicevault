import React, { useCallback, useEffect, useState } from 'react';
import { Link, LogOut, Settings, Trash2, UserPlus, Users, X } from 'lucide-react';

import { projectApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { AccessRequestList } from './AccessRequestList';
import { permalinkFor } from '../hooks/useRoute';
import { Group, Project, ProjectDetail, ProjectRole } from '../types';
import { useCan } from '../hooks/useCan';
import { errorFrom } from '../utils/errors';

interface ProjectSettingsModalProps {
  project: Project;
  isOpen: boolean;
  onClose: () => void;
  onChanged: () => void;
  onDeletedOrLeft: () => void;
}

const ROLES: ProjectRole[] = ['owner', 'editor', 'viewer'];
// Owners are always added in person, so a group change can never orphan a project.
const GROUP_ROLES: ProjectRole[] = ['editor', 'viewer'];

export const ProjectSettingsModal: React.FC<ProjectSettingsModalProps> = ({
  project,
  isOpen,
  onClose,
  onChanged,
  onDeletedOrLeft,
}) => {
  const { user, mode } = useAuth();
  const can = useCan();
  const [groupSearch, setGroupSearch] = useState('');
  const [groupResults, setGroupResults] = useState<Group[]>([]);
  const [newGroupRole, setNewGroupRole] = useState<ProjectRole>('viewer');
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [newMemberEmail, setNewMemberEmail] = useState('');
  const [newMemberRole, setNewMemberRole] = useState<ProjectRole>('viewer');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const loaded = await projectApi.get(project.id);
      setDetail(loaded);
      setName(loaded.name);
      setDescription(loaded.description ?? '');
    } catch (err) {
      console.error('Failed to load project:', err);
      setError('Failed to load project details.');
    } finally {
      setIsLoading(false);
    }
  }, [project.id]);

  useEffect(() => {
    if (isOpen) {
      load();
    }
  }, [isOpen, load]);

  const canManage = detail?.my_role === 'owner' && can('projects.manage', project.id);

  useEffect(() => {
    if (!canManage) return;
    const query = groupSearch.trim();
    if (!query) {
      setGroupResults([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      projectApi
        .searchGroups(query)
        .then((results) => {
          if (!cancelled) setGroupResults(results);
        })
        .catch(() => undefined);
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [groupSearch, canManage]);

  if (!isOpen) {
    return null;
  }

  const isOwner = detail?.my_role === 'owner';
  const ownerCount = detail?.members.filter((m) => m.role === 'owner').length ?? 0;
  const isLastOwner = isOwner && ownerCount <= 1;
  const isDirectMember = detail?.members.some((m) => m.user_id === user?.id) ?? false;
  const accessVia = detail?.my_access_via ?? [];

  const refresh = async () => {
    await load();
    onChanged();
  };

  const handleSaveDetails = async () => {
    setError(null);
    try {
      await projectApi.update(project.id, {
        name: name.trim(),
        description: description.trim() || null,
      });
      await refresh();
    } catch (err) {
      setError(errorFrom(err, 'Failed to update project.'));
    }
  };

  const handleAddMember = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newMemberEmail.trim()) {
      return;
    }
    setError(null);
    try {
      await projectApi.addMember(project.id, newMemberEmail.trim(), newMemberRole);
      setNewMemberEmail('');
      setNewMemberRole('viewer');
      await refresh();
    } catch (err) {
      setError(errorFrom(err, 'Failed to add member.'));
    }
  };

  const handleRoleChange = async (userId: string, role: ProjectRole) => {
    setError(null);
    try {
      await projectApi.updateMember(project.id, userId, role);
      await refresh();
    } catch (err) {
      setError(errorFrom(err, 'Failed to change role.'));
    }
  };

  const handleRemoveMember = async (userId: string) => {
    setError(null);
    try {
      await projectApi.removeMember(project.id, userId);
      await refresh();
    } catch (err) {
      setError(errorFrom(err, 'Failed to remove member.'));
    }
  };

  const handleAddGroup = async (group: Group) => {
    if (
      group.is_builtin &&
      !window.confirm(`Share "${project.name}" with every user as ${newGroupRole}s?`)
    ) {
      return;
    }
    setError(null);
    try {
      await projectApi.addGroup(project.id, group.id, newGroupRole);
      setGroupSearch('');
      setGroupResults([]);
      await refresh();
    } catch (err) {
      setError(errorFrom(err, 'Failed to share with the group.'));
    }
  };

  const handleGroupRoleChange = async (groupId: string, role: ProjectRole) => {
    setError(null);
    try {
      await projectApi.updateGroup(project.id, groupId, role);
      await refresh();
    } catch (err) {
      setError(errorFrom(err, 'Failed to change the group role.'));
    }
  };

  const handleRemoveGroup = async (groupId: string) => {
    setError(null);
    try {
      await projectApi.removeGroup(project.id, groupId);
      await refresh();
    } catch (err) {
      setError(errorFrom(err, 'Failed to remove the group.'));
    }
  };

  const handleLeave = async () => {
    if (!user) {
      return;
    }
    setError(null);
    try {
      await projectApi.removeMember(project.id, user.id);
      onChanged();
      onDeletedOrLeft();
    } catch (err) {
      setError(errorFrom(err, 'Failed to leave project.'));
    }
  };

  const handleDelete = async () => {
    if (!window.confirm("Delete this project? Entries revert to their owners' private space.")) {
      return;
    }
    setError(null);
    try {
      await projectApi.remove(project.id);
      onChanged();
      onDeletedOrLeft();
    } catch (err) {
      setError(errorFrom(err, 'Failed to delete project.'));
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-gray-100 p-2 text-gray-700">
              <Settings className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Project Settings</h2>
              <p className="text-sm text-gray-500">{project.name}</p>
            </div>
          </div>
          <button
            onClick={() => void navigator.clipboard?.writeText(permalinkFor(project.id))}
            className="ml-auto mr-1 rounded-md p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
            aria-label="Copy project link"
            title="Copy project link"
          >
            <Link className="h-5 w-5" />
          </button>
          <button
            onClick={onClose}
            className="rounded-md p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-5 py-4">
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          {isLoading || !detail ? (
            <p className="text-sm text-gray-500">Loading…</p>
          ) : (
            <>
              {canManage && (
                <section className="space-y-3">
                  <h3 className="text-sm font-semibold text-gray-900">Details</h3>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-primary-500"
                    maxLength={255}
                  />
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-primary-500"
                    rows={2}
                    maxLength={5000}
                    placeholder="Description (optional)"
                  />
                  <button
                    onClick={handleSaveDetails}
                    disabled={!name.trim()}
                    className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Save
                  </button>
                </section>
              )}

              <section className="space-y-3">
                <h3 className="text-sm font-semibold text-gray-900">
                  Members ({detail.members.length})
                </h3>
                <div className="space-y-2">
                  {detail.members.map((member) => (
                    <div
                      key={member.user_id}
                      className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 px-3 py-2"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-gray-900">
                          {member.display_name}
                        </p>
                        <p className="truncate text-xs text-gray-500">{member.email}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        {canManage ? (
                          <select
                            value={member.role}
                            onChange={(e) =>
                              handleRoleChange(member.user_id, e.target.value as ProjectRole)
                            }
                            className="rounded-md border border-gray-300 px-2 py-1 text-xs focus:border-primary-500 focus:outline-none"
                          >
                            {ROLES.map((role) => (
                              <option key={role} value={role}>
                                {role}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <span className="rounded bg-gray-100 px-2 py-1 text-xs uppercase text-gray-500">
                            {member.role}
                          </span>
                        )}
                        {canManage && member.user_id !== user?.id && (
                          <button
                            onClick={() => handleRemoveMember(member.user_id)}
                            className="rounded-md p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-red-600"
                            aria-label={`Remove ${member.display_name}`}
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {canManage && (
                  <form className="flex items-center gap-2" onSubmit={handleAddMember}>
                    <input
                      type="email"
                      value={newMemberEmail}
                      onChange={(e) => setNewMemberEmail(e.target.value)}
                      className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-primary-500"
                      placeholder="member@example.com"
                    />
                    <select
                      value={newMemberRole}
                      onChange={(e) => setNewMemberRole(e.target.value as ProjectRole)}
                      className="rounded-md border border-gray-300 px-2 py-2 text-sm focus:border-primary-500 focus:outline-none"
                    >
                      {ROLES.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                    <button
                      type="submit"
                      disabled={!newMemberEmail.trim()}
                      className="inline-flex items-center gap-1 rounded-lg bg-primary-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <UserPlus className="h-4 w-4" />
                      Add
                    </button>
                  </form>
                )}
              </section>

              {(canManage || (detail.groups?.length ?? 0) > 0) && (
                <section className="space-y-3">
                  <h3 className="text-sm font-semibold text-gray-900">
                    Groups ({detail.groups?.length ?? 0})
                  </h3>
                  <div className="space-y-2">
                    {(detail.groups ?? []).map((group) => (
                      <div
                        key={group.group_id}
                        className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 px-3 py-2"
                      >
                        <div className="flex min-w-0 items-center gap-2">
                          <Users className="h-4 w-4 shrink-0 text-gray-400" />
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium text-gray-900">
                              {group.name}
                            </p>
                            <p className="text-xs text-gray-500">
                              {group.member_count === null
                                ? 'Every user'
                                : `${group.member_count} member${group.member_count === 1 ? '' : 's'}`}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {canManage ? (
                            <select
                              value={group.role}
                              aria-label={`Role of ${group.name}`}
                              onChange={(e) =>
                                handleGroupRoleChange(group.group_id, e.target.value as ProjectRole)
                              }
                              className="rounded-md border border-gray-300 px-2 py-1 text-xs focus:border-primary-500 focus:outline-none"
                            >
                              {GROUP_ROLES.map((role) => (
                                <option key={role} value={role}>
                                  {role}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <span className="rounded bg-gray-100 px-2 py-1 text-xs uppercase text-gray-500">
                              {group.role}
                            </span>
                          )}
                          {canManage && (
                            <button
                              onClick={() => handleRemoveGroup(group.group_id)}
                              className="rounded-md p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-red-600"
                              aria-label={`Remove group ${group.name}`}
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                  {canManage && (
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          value={groupSearch}
                          onChange={(e) => setGroupSearch(e.target.value)}
                          className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-primary-500"
                          placeholder="Share with a group…"
                          aria-label="Search groups"
                        />
                        <select
                          value={newGroupRole}
                          onChange={(e) => setNewGroupRole(e.target.value as ProjectRole)}
                          aria-label="Role for the group"
                          className="rounded-md border border-gray-300 px-2 py-2 text-sm focus:border-primary-500 focus:outline-none"
                        >
                          {GROUP_ROLES.map((role) => (
                            <option key={role} value={role}>
                              {role}
                            </option>
                          ))}
                        </select>
                      </div>
                      {groupResults.length > 0 && (
                        <div
                          className="divide-y rounded-md border"
                          role="listbox"
                          aria-label="Groups"
                        >
                          {groupResults
                            .filter((group) => !detail.groups?.some((g) => g.group_id === group.id))
                            .map((group) => (
                              <button
                                key={group.id}
                                type="button"
                                role="option"
                                aria-selected={false}
                                onClick={() => handleAddGroup(group)}
                                className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-gray-50"
                              >
                                <span>{group.name}</span>
                                <span className="text-xs text-gray-500">
                                  {group.is_builtin
                                    ? 'every user'
                                    : `${group.member_count} members`}
                                </span>
                              </button>
                            ))}
                        </div>
                      )}
                    </div>
                  )}
                </section>
              )}

              {canManage && mode === 'oidc' && (
                <section className="space-y-3">
                  <h3 className="text-sm font-semibold text-gray-900">Access requests</h3>
                  <AccessRequestList projectId={project.id} onChanged={refresh} />
                </section>
              )}

              <section className="flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-4">
                {!isDirectMember && accessVia.length > 0 && (
                  <p className="text-xs text-gray-500">
                    Your access comes from group {accessVia.join(', ')}.
                  </p>
                )}
                {!isLastOwner && isDirectMember && (
                  <button
                    onClick={handleLeave}
                    className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100"
                  >
                    <LogOut className="h-4 w-4" />
                    Leave project
                  </button>
                )}
                {canManage && (
                  <button
                    onClick={handleDelete}
                    className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-50"
                  >
                    <Trash2 className="h-4 w-4" />
                    Delete project
                  </button>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

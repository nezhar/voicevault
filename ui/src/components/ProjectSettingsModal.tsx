import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { LogOut, Settings, Trash2, UserPlus, X } from 'lucide-react';

import { projectApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { Project, ProjectDetail, ProjectRole } from '../types';

interface ProjectSettingsModalProps {
  project: Project;
  isOpen: boolean;
  onClose: () => void;
  onChanged: () => void;
  onDeletedOrLeft: () => void;
}

const ROLES: ProjectRole[] = ['owner', 'editor', 'viewer'];

export const ProjectSettingsModal: React.FC<ProjectSettingsModalProps> = ({
  project,
  isOpen,
  onClose,
  onChanged,
  onDeletedOrLeft,
}) => {
  const { user } = useAuth();
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

  if (!isOpen) {
    return null;
  }

  const isOwner = detail?.my_role === 'owner';
  const ownerCount = detail?.members.filter((m) => m.role === 'owner').length ?? 0;
  const isLastOwner = isOwner && ownerCount <= 1;

  const errorFrom = (err: unknown, fallback: string): string => {
    const detailMessage = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
    return detailMessage || fallback;
  };

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
              {isOwner && (
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
                        {isOwner ? (
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
                        {isOwner && member.user_id !== user?.id && (
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

                {isOwner && (
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

              <section className="flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-4">
                {!isLastOwner && (
                  <button
                    onClick={handleLeave}
                    className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100"
                  >
                    <LogOut className="h-4 w-4" />
                    Leave project
                  </button>
                )}
                {isOwner && (
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

import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Check, FolderInput, Search, X } from 'lucide-react';

import { Entry, Project, roleAtLeast } from '../types';

interface MoveToProjectModalProps {
  entry: Entry;
  projects: Project[];
  isOpen: boolean;
  onClose: () => void;
  onMove: (entry: Entry, projectId: string | null) => Promise<void>;
}

export const MoveToProjectModal: React.FC<MoveToProjectModalProps> = ({
  entry,
  projects,
  isOpen,
  onClose,
  onMove,
}) => {
  const currentId = entry.project_id ?? null;
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(currentId);
  const [isMoving, setIsMoving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  const moveTargets = projects.filter((p) => roleAtLeast(p.my_role, 'editor'));
  const query = search.trim().toLowerCase();
  const filteredTargets = query
    ? moveTargets.filter((p) => p.name.toLowerCase().includes(query))
    : moveTargets;
  const canMove = !isMoving && selectedId !== currentId;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canMove) return;
    setIsMoving(true);
    setError(null);
    try {
      await onMove(entry, selectedId);
      onClose();
    } catch (err) {
      console.error('Failed to move entry:', err);
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
      setError(detail || 'Failed to move entry. Please try again.');
    } finally {
      setIsMoving(false);
    }
  };

  const renderRow = (id: string | null, label: string) => {
    const isSelected = selectedId === id;
    const isCurrent = currentId === id;
    return (
      <button
        key={id ?? '__private__'}
        type="button"
        onClick={() => setSelectedId(id)}
        disabled={isMoving}
        aria-pressed={isSelected}
        className={`flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors disabled:opacity-50 ${
          isSelected
            ? 'bg-primary-50 font-medium text-primary-700'
            : 'text-gray-700 hover:bg-gray-50'
        }`}
      >
        <span className="flex min-w-0 items-center gap-2">
          {isSelected ? (
            <Check className="h-4 w-4 flex-shrink-0" />
          ) : (
            <span className="w-4 flex-shrink-0" aria-hidden="true" />
          )}
          <span className="truncate">{label}</span>
        </span>
        {isCurrent && (
          <span className="flex-shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
            current
          </span>
        )}
      </button>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-gray-100 p-2 text-gray-700">
              <FolderInput className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <h2 className="text-lg font-semibold text-gray-900">Move to project</h2>
              <p className="truncate text-sm text-gray-500" title={entry.title}>
                {entry.title}
              </p>
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

        <form className="space-y-3 px-5 pb-4" onSubmit={handleSubmit}>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-md border border-gray-300 py-2 pl-9 pr-3 text-sm focus:border-primary-500 focus:outline-none focus:ring-primary-500"
              placeholder="Search projects..."
              aria-label="Search projects"
              autoFocus
              disabled={isMoving}
            />
          </div>

          <div className="max-h-60 space-y-0.5 overflow-y-auto rounded-md border border-gray-200 p-1">
            {renderRow(null, 'Private (only me)')}
            {filteredTargets.map((target) => renderRow(target.id, target.name))}
            {filteredTargets.length === 0 && (
              <p className="px-3 py-2 text-sm text-gray-400">No matching projects</p>
            )}
          </div>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100"
              disabled={isMoving}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canMove}
              className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isMoving ? 'Moving...' : 'Move'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

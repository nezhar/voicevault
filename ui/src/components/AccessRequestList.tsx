import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Check, X } from 'lucide-react';

import { projectApi } from '../services/api';
import { AccessRequest, ProjectRole } from '../types';

interface AccessRequestListProps {
  projectId: string;
  onChanged: () => void;
}

const ROLES: ProjectRole[] = ['viewer', 'editor', 'owner'];

export const AccessRequestList: React.FC<AccessRequestListProps> = ({ projectId, onChanged }) => {
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [roles, setRoles] = useState<Record<string, ProjectRole>>({});
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = useCallback(async () => {
    setIsLoading(true);
    try {
      setRequests(await projectApi.listAccessRequests(projectId, 'pending'));
    } catch {
      setError('Failed to load access requests.');
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const errorFrom = (err: unknown, fallback: string): string => {
    const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
    return detail || fallback;
  };

  const decide = async (request: AccessRequest, approve: boolean) => {
    setError(null);
    try {
      if (approve) {
        await projectApi.approveRequest(projectId, request.id, roles[request.id] ?? 'viewer');
      } else {
        await projectApi.denyRequest(projectId, request.id);
      }
      setRequests((current) => current.filter((item) => item.id !== request.id));
      onChanged();
    } catch (err) {
      setError(errorFrom(err, 'Failed to update the request.'));
    }
  };

  if (isLoading) {
    return <p className="text-sm text-gray-500">Loading…</p>;
  }

  return (
    <div className="space-y-2">
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {requests.length === 0 && <p className="text-sm text-gray-500">No pending requests.</p>}

      {requests.map((request) => (
        <div key={request.id} className="space-y-2 rounded-lg border border-gray-200 px-3 py-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-gray-900">{request.display_name}</p>
            <p className="truncate text-xs text-gray-500">{request.email}</p>
            {request.message && <p className="mt-1 text-xs text-gray-600">{request.message}</p>}
          </div>
          <div className="flex items-center gap-2">
            <select
              value={roles[request.id] ?? 'viewer'}
              onChange={(event) =>
                setRoles((current) => ({
                  ...current,
                  [request.id]: event.target.value as ProjectRole,
                }))
              }
              aria-label={`Role for ${request.display_name}`}
              className="rounded-md border border-gray-300 px-2 py-1 text-xs focus:border-primary-500 focus:outline-none"
            >
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
            <button
              onClick={() => decide(request, true)}
              aria-label={`Approve ${request.display_name}`}
              className="inline-flex items-center gap-1 rounded-lg bg-primary-600 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-primary-700"
            >
              <Check className="h-3 w-3" />
              Approve
            </button>
            <button
              onClick={() => decide(request, false)}
              aria-label={`Deny ${request.display_name}`}
              className="inline-flex items-center gap-1 rounded-lg px-3 py-1 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-100"
            >
              <X className="h-3 w-3" />
              Deny
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};

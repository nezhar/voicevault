import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { FolderLock, Loader2 } from 'lucide-react';

import { projectApi } from '../services/api';
import { ProjectPreview } from '../types';

interface ProjectAccessRequestProps {
  projectId: string;
  onAccessGranted: () => void;
}

export const ProjectAccessRequest: React.FC<ProjectAccessRequestProps> = ({
  projectId,
  onAccessGranted,
}) => {
  const [preview, setPreview] = useState<ProjectPreview | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setPreview(await projectApi.preview(projectId));
    } catch {
      setPreview(null);
      setError('This project does not exist or is no longer available.');
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  // An approval that landed while this page was open: hand back to the app so
  // it can refetch projects and render the real project view.
  useEffect(() => {
    if (preview?.my_role) {
      onAccessGranted();
    }
  }, [preview, onAccessGranted]);

  const errorFrom = (err: unknown, fallback: string): string => {
    const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
    return detail || fallback;
  };

  const handleRequest = async () => {
    setIsSubmitting(true);
    setError(null);
    try {
      const request = await projectApi.requestAccess(projectId, message.trim() || undefined);
      setPreview((current) =>
        current ? { ...current, request_status: request.status, request_id: request.id } : current,
      );
      setMessage('');
    } catch (err) {
      setError(errorFrom(err, 'Could not send the request. Please try again.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = async () => {
    if (!preview?.request_id) {
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      await projectApi.cancelRequest(projectId, preview.request_id);
      setPreview({ ...preview, request_status: null, request_id: null });
    } catch (err) {
      setError(errorFrom(err, 'Could not cancel the request.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-500">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="mx-auto max-w-md rounded-2xl border border-gray-200 bg-white p-6 text-center">
        <p className="text-sm text-gray-600">{error}</p>
      </div>
    );
  }

  const status = preview.request_status;
  const showRequestButton = preview.can_request && status !== 'pending';

  return (
    <div className="mx-auto max-w-md space-y-4 rounded-2xl border border-gray-200 bg-white p-6">
      <div className="flex items-center gap-3">
        <div className="rounded-full bg-gray-100 p-2 text-gray-700">
          <FolderLock className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <h2 className="truncate text-lg font-semibold text-gray-900">{preview.name}</h2>
          <p className="text-sm text-gray-500">You do not have access to this project.</p>
        </div>
      </div>

      {preview.owners.length > 0 && (
        <p className="text-sm text-gray-600">
          Owners:{' '}
          {preview.owners.map((owner) => `${owner.display_name} (${owner.email})`).join(', ')}
        </p>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {status === 'pending' && (
        <div className="space-y-2">
          <p className="text-sm text-gray-700">Request sent — waiting for an owner to review it.</p>
          <button
            onClick={handleCancel}
            disabled={isSubmitting}
            className="rounded-lg px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 disabled:opacity-50"
          >
            Cancel request
          </button>
        </div>
      )}

      {status === 'denied' && (
        <p className="text-sm text-gray-700">Your previous request was declined.</p>
      )}

      {showRequestButton && (
        <div className="space-y-2">
          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            rows={2}
            maxLength={500}
            placeholder="Why do you need access? (optional)"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-primary-500"
          />
          <button
            onClick={handleRequest}
            disabled={isSubmitting}
            className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {status === 'denied' ? 'Request again' : 'Request access'}
          </button>
        </div>
      )}
    </div>
  );
};

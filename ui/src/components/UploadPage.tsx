import React, { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2, Upload } from 'lucide-react';

import {
  UploadLinkCredentials,
  UploadLinkError,
  checkUploadFile,
  fetchUploadLink,
  parseUploadFragment,
  sendUploadLinkFile,
} from '../services/uploadLink';
import { UploadLinkCompleted, UploadLinkInfo, UploadLinkState } from '../types';
import { formatBytes, formatDateTime } from '../utils/format';

type Phase =
  | { kind: 'loading' }
  | { kind: 'closed'; title: string; message: string; canRetry?: boolean }
  | { kind: 'ready' }
  | { kind: 'sending'; progress: number }
  | { kind: 'done'; result: UploadLinkCompleted };

// After these the link can never succeed; other failures are worth a retry.
const FINAL_STATUSES = new Set([401, 403, 404, 409, 410]);

const ASK_AGAIN = 'Ask your assistant for a new upload link.';

const INCOMPLETE: Phase = {
  kind: 'closed',
  title: 'This upload link is incomplete',
  message: 'Open the complete link from your assistant; everything after the # is part of it.',
};

const closedForState = (state: UploadLinkState): Phase => {
  switch (state) {
    case 'completed':
      return {
        kind: 'closed',
        title: 'This upload link was already used',
        message: 'The file arrived. You can return to your assistant.',
      };
    case 'uploading':
      return {
        kind: 'closed',
        title: 'An upload for this link is in progress',
        message: 'Another upload is still being stored. Check back with your assistant shortly.',
      };
    case 'expired':
      return { kind: 'closed', title: 'This upload link has expired', message: ASK_AGAIN };
    default:
      return { kind: 'ready' };
  }
};

const closedForError = (error: unknown): Phase => {
  const status = error instanceof UploadLinkError ? error.status : 0;
  const detail = error instanceof Error ? error.message : 'Something went wrong.';
  if (status === 401) {
    return {
      kind: 'closed',
      title: 'This upload link is not valid',
      message: `It may have been revoked or copied incompletely. ${ASK_AGAIN}`,
    };
  }
  if (status === 410) {
    return { kind: 'closed', title: 'This upload link has expired', message: ASK_AGAIN };
  }
  return {
    kind: 'closed',
    title: 'The upload link could not be opened',
    message: detail,
    canRetry: !FINAL_STATUSES.has(status),
  };
};

const Shell: React.FC<{ subtitle: string; children: React.ReactNode }> = ({
  subtitle,
  children,
}) => (
  <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
    <div className="max-w-md w-full space-y-8">
      <div className="text-center">
        <div className="mx-auto h-16 w-16 bg-primary-600 rounded-full flex items-center justify-center">
          <Upload className="h-8 w-8 text-white" />
        </div>
        <h1 className="mt-6 text-3xl font-extrabold text-gray-900">Upload to VoiceVault</h1>
        <p className="mt-2 text-sm text-gray-600">{subtitle}</p>
      </div>
      <div className="bg-white shadow rounded-lg p-6 space-y-4">{children}</div>
    </div>
  </div>
);

export const UploadPage: React.FC = () => {
  // Read once: the fragment is removed from the address bar right after.
  const [credentials] = useState<UploadLinkCredentials | null>(() =>
    parseUploadFragment(window.location.hash),
  );
  const [phase, setPhase] = useState<Phase>(credentials ? { kind: 'loading' } : INCOMPLETE);
  const [info, setInfo] = useState<UploadLinkInfo | null>(null);
  const [file, setFile] = useState<File | null>(null);
  // A file problem blocks uploading; a failed attempt only asks for a retry.
  const [fileProblem, setFileProblem] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    // Keep the link secret out of browser history and synced tabs.
    if (window.location.hash) {
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
    }
  }, []);

  useEffect(() => {
    if (!credentials) {
      return;
    }
    let cancelled = false;
    setPhase({ kind: 'loading' });
    fetchUploadLink(credentials)
      .then((loaded) => {
        if (!cancelled) {
          setInfo(loaded);
          setPhase(closedForState(loaded.state));
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setPhase(closedForError(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [credentials, attempt]);

  const chooseFile = (selected: File | undefined) => {
    if (!selected || !info) {
      return;
    }
    setFile(selected);
    setFileProblem(checkUploadFile(selected, info));
    setUploadError(null);
  };

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(false);
    chooseFile(event.dataTransfer.files?.[0]);
  };

  const handleUpload = async () => {
    if (!credentials || !info || !file) {
      return;
    }
    const problem = checkUploadFile(file, info);
    setFileProblem(problem);
    if (problem) {
      return;
    }
    setUploadError(null);
    setPhase({ kind: 'sending', progress: 0 });
    try {
      const result = await sendUploadLinkFile(credentials, file, (progress) =>
        setPhase({ kind: 'sending', progress }),
      );
      setPhase({ kind: 'done', result });
    } catch (err) {
      const status = err instanceof UploadLinkError ? err.status : 0;
      const message = err instanceof Error ? err.message : 'The upload failed.';
      if (FINAL_STATUSES.has(status)) {
        setPhase({ kind: 'closed', title: 'The upload could not be completed', message });
      } else {
        setPhase({ kind: 'ready' });
        setUploadError(message);
      }
    }
  };

  const subtitle = info?.title
    ? `For “${info.title}”`
    : 'Send a recording to VoiceVault for transcription';

  if (phase.kind === 'loading') {
    return (
      <Shell subtitle="Checking your upload link…">
        <div className="flex justify-center py-6" aria-label="Loading">
          <Loader2 className="h-8 w-8 animate-spin text-primary-600" />
        </div>
      </Shell>
    );
  }

  if (phase.kind === 'closed') {
    return (
      <Shell subtitle={subtitle}>
        <div className="flex items-start gap-3" role="alert">
          <AlertCircle className="h-6 w-6 flex-shrink-0 text-red-500" />
          <div>
            <h2 className="font-semibold text-gray-900">{phase.title}</h2>
            <p className="mt-1 text-sm text-gray-600">{phase.message}</p>
          </div>
        </div>
        {phase.canRetry && (
          <button
            type="button"
            onClick={() => setAttempt((value) => value + 1)}
            className="w-full py-2 px-4 rounded-md text-sm font-medium text-primary-700 border border-primary-300 hover:bg-primary-50"
          >
            Try again
          </button>
        )}
      </Shell>
    );
  }

  if (phase.kind === 'done') {
    return (
      <Shell subtitle={subtitle}>
        <div className="flex items-start gap-3" role="status">
          <CheckCircle2 className="h-6 w-6 flex-shrink-0 text-green-600" />
          <div>
            <h2 className="font-semibold text-gray-900">Upload complete</h2>
            <p className="mt-1 text-sm text-gray-600">
              “{phase.result.entry.title}” is being transcribed. You can return to your assistant
              now.
            </p>
          </div>
        </div>
      </Shell>
    );
  }

  const sending = phase.kind === 'sending';
  const error = fileProblem ?? uploadError;
  const percent = sending ? Math.round(phase.progress * 100) : 0;
  const accept = info?.supported_formats.map((format) => `.${format}`).join(',');

  return (
    <Shell subtitle={subtitle}>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        aria-label="File drop zone"
        className={`flex justify-center px-6 pt-5 pb-6 border-2 border-dashed rounded-md transition-colors ${
          isDragging ? 'border-primary-500 bg-primary-50' : 'border-gray-300'
        }`}
      >
        <div className="space-y-1 text-center">
          <Upload className="mx-auto h-12 w-12 text-gray-400" />
          <div className="flex justify-center text-sm text-gray-600">
            <label
              htmlFor="upload-link-file"
              className="relative cursor-pointer bg-white rounded-md font-medium text-primary-600 hover:text-primary-500 focus-within:outline-none focus-within:ring-2 focus-within:ring-offset-2 focus-within:ring-primary-500"
            >
              <span>Choose a file</span>
              <input
                id="upload-link-file"
                type="file"
                className="sr-only"
                accept={accept}
                disabled={sending}
                onChange={(event) => chooseFile(event.target.files?.[0])}
              />
            </label>
            <p className="pl-1">or drag and drop</p>
          </div>
          <p className="text-xs text-gray-500">
            {info?.supported_formats.join(', ').toUpperCase()} · up to{' '}
            {formatBytes(info?.max_bytes ?? 0)}
          </p>
          {info?.filename && (
            <p className="text-xs text-gray-500">Expected file: {info.filename}</p>
          )}
          {file && (
            <p className="text-sm text-primary-600 font-medium">
              Selected: {file.name} ({formatBytes(file.size)})
            </p>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 text-sm text-red-700" role="alert">
          <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {sending && (
        <div className="space-y-1">
          <div
            className="h-2 w-full rounded-full bg-gray-200 overflow-hidden"
            role="progressbar"
            aria-label="Upload progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
          >
            <div
              className="h-full bg-primary-600 transition-all"
              style={{ width: `${percent}%` }}
            />
          </div>
          <p className="text-xs text-gray-500">
            {percent < 100 ? `Uploading… ${percent}%` : 'Finishing up…'} Keep this page open until
            the upload is done.
          </p>
        </div>
      )}

      <button
        type="button"
        onClick={handleUpload}
        disabled={!file || !!fileProblem || sending}
        className="w-full flex justify-center items-center gap-2 py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {sending && <Loader2 className="h-4 w-4 animate-spin" />}
        {sending ? 'Uploading…' : uploadError ? 'Try again' : 'Upload'}
      </button>

      {info && (
        <p className="text-xs text-gray-500 text-center">
          This link works once and must be used before {formatDateTime(info.expires_at)}.
        </p>
      )}
    </Shell>
  );
};

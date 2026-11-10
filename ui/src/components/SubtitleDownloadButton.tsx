import React, { useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { Entry } from '../types';
import { entryApi } from '../services/api';
import { errorFrom } from '../utils/errors';
import { hasTimestamps, triggerBrowserDownload } from '../utils/download';

interface SubtitleDownloadButtonProps {
  entry: Entry;
  /** `compact` matches the small text buttons in the chat header. */
  variant?: 'compact' | 'default';
}

const VARIANT_CLASSES: Record<NonNullable<SubtitleDownloadButtonProps['variant']>, string> = {
  compact:
    'inline-flex items-center px-2 py-1 text-xs rounded text-primary-600 hover:text-primary-700 hover:bg-primary-50',
  default:
    'inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50',
};

/** Downloads the entry's transcript as an .srt file; renders nothing without timestamps. */
export const SubtitleDownloadButton: React.FC<SubtitleDownloadButtonProps> = ({
  entry,
  variant = 'default',
}) => {
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!hasTimestamps(entry)) return null;

  const handleDownload = async () => {
    setIsDownloading(true);
    setError(null);
    try {
      const { blob, filename } = await entryApi.downloadSubtitles(entry.id, 'srt');
      triggerBrowserDownload(blob, filename);
    } catch (err) {
      setError(errorFrom(err, 'Failed to download subtitles.'));
    } finally {
      setIsDownloading(false);
    }
  };

  const iconClass = variant === 'compact' ? 'h-3 w-3 mr-1' : 'h-4 w-4';

  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={handleDownload}
        disabled={isDownloading}
        className={`${VARIANT_CLASSES[variant]} transition-colors disabled:cursor-wait disabled:opacity-60`}
        aria-label="Download transcript as SRT subtitles"
        title="Download transcript as SRT subtitles"
      >
        {isDownloading ? (
          <Loader2 className={`${iconClass} animate-spin`} />
        ) : (
          <Download className={iconClass} />
        )}
        {variant === 'compact' ? 'SRT' : 'Download SRT'}
      </button>
      {error && (
        <span role="alert" className="text-xs text-red-600">
          {error}
        </span>
      )}
    </span>
  );
};

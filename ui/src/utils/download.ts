import { Entry } from '../types';

/** True when the entry has ASR timestamps, i.e. subtitles can be exported. */
export const hasTimestamps = (
  entry: Pick<Entry, 'transcript_words' | 'transcript_segments'>,
): boolean =>
  (entry.transcript_segments?.length ?? 0) > 0 || (entry.transcript_words?.length ?? 0) > 0;

/**
 * Filename from a Content-Disposition header, preferring the RFC 5987
 * `filename*` (UTF-8) form over the plain ASCII `filename`.
 */
export const filenameFromContentDisposition = (
  header: string | null | undefined,
): string | null => {
  if (!header) return null;

  const extended = /filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)/.exec(header);
  if (extended) {
    try {
      const decoded = decodeURIComponent(extended[1].trim());
      if (decoded) return decoded;
    } catch {
      // Malformed percent-encoding: fall through to the plain filename.
    }
  }

  const plain = /filename\s*=\s*(?:"([^"]*)"|([^;]+))/.exec(header);
  const value = (plain?.[1] ?? plain?.[2] ?? '').trim();
  return value || null;
};

/** Save a Blob through the browser's download flow. */
export const triggerBrowserDownload = (blob: Blob, filename: string): void => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoke on the next tick: some browsers start the download asynchronously.
  setTimeout(() => URL.revokeObjectURL(url), 0);
};

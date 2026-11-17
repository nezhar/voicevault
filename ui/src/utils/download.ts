import { Entry } from '../types';

const isTime = (value: unknown): boolean => typeof value === 'number' && Number.isFinite(value);

/** Mirrors the API's subtitle normalization: finite times and non-blank text. */
const hasUsableItem = (items: unknown, textKey: 'text' | 'word'): boolean =>
  Array.isArray(items) &&
  items.some((item) => {
    if (!item || typeof item !== 'object') return false;
    const record = item as Record<string, unknown>;
    const text = record[textKey];
    return (
      typeof text === 'string' && text.trim() !== '' && isTime(record.start) && isTime(record.end)
    );
  });

/** True when the entry has usable ASR timestamps, i.e. subtitles can be exported. */
export const hasTimestamps = (
  entry: Pick<Entry, 'transcript_words' | 'transcript_segments'>,
): boolean =>
  hasUsableItem(entry.transcript_segments, 'text') || hasUsableItem(entry.transcript_words, 'word');

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

import { afterEach, describe, expect, it, vi } from 'vitest';
import { filenameFromContentDisposition, hasTimestamps, triggerBrowserDownload } from './download';

describe('hasTimestamps', () => {
  it('is true with segments or words', () => {
    expect(hasTimestamps({ transcript_segments: [{ text: 'a', start: 0, end: 1 }] })).toBe(true);
    expect(hasTimestamps({ transcript_words: [{ word: 'a', start: 0, end: 1 }] })).toBe(true);
  });

  it('is false without any', () => {
    expect(hasTimestamps({})).toBe(false);
    expect(hasTimestamps({ transcript_segments: [], transcript_words: [] })).toBe(false);
  });
});

describe('filenameFromContentDisposition', () => {
  it('prefers the UTF-8 filename*', () => {
    expect(
      filenameFromContentDisposition(
        `attachment; filename="transcript_Groesse.srt"; filename*=UTF-8''transcript_Gr%C3%B6%C3%9Fe.srt`,
      ),
    ).toBe('transcript_Größe.srt');
  });

  it('falls back to the plain filename', () => {
    expect(filenameFromContentDisposition('attachment; filename="transcript_a.srt"')).toBe(
      'transcript_a.srt',
    );
    expect(filenameFromContentDisposition('attachment; filename=transcript_b.srt')).toBe(
      'transcript_b.srt',
    );
    expect(
      filenameFromContentDisposition(`attachment; filename="ok.srt"; filename*=UTF-8''%E0%A4%A`),
    ).toBe('ok.srt');
  });

  it('returns null without a filename', () => {
    expect(filenameFromContentDisposition(undefined)).toBeNull();
    expect(filenameFromContentDisposition('attachment')).toBeNull();
  });
});

describe('triggerBrowserDownload', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('clicks a temporary link and revokes the object URL', () => {
    vi.useFakeTimers();
    const createObjectURL = vi.fn(() => 'blob:test');
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      expect(this.download).toBe('transcript_x.srt');
      expect(this.getAttribute('href')).toBe('blob:test');
    });

    triggerBrowserDownload(new Blob(['1']), 'transcript_x.srt');

    expect(click).toHaveBeenCalledOnce();
    expect(document.querySelector('a[download]')).toBeNull();
    vi.runAllTimers();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test');
  });
});

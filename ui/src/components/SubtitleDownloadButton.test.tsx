import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SubtitleDownloadButton } from './SubtitleDownloadButton';
import { Entry } from '../types';

const { downloadSubtitles, triggerBrowserDownload } = vi.hoisted(() => ({
  downloadSubtitles: vi.fn(),
  triggerBrowserDownload: vi.fn(),
}));

vi.mock('../services/api', () => ({ entryApi: { downloadSubtitles } }));
vi.mock('../utils/download', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../utils/download')>()),
  triggerBrowserDownload,
}));

const baseEntry: Entry = {
  id: 'entry-1',
  title: 'Weekly sync',
  source_type: 'upload',
  status: 'READY',
  archived: false,
  has_audio: true,
  transcript: 'Hello there.',
  created_at: '2026-11-10T10:00:00Z',
  updated_at: '2026-11-10T10:00:00Z',
};

const timedEntry: Entry = {
  ...baseEntry,
  transcript_segments: [{ text: 'Hello there.', start: 0, end: 1.2 }],
};

describe('SubtitleDownloadButton', () => {
  beforeEach(() => {
    downloadSubtitles.mockReset();
    triggerBrowserDownload.mockReset();
  });

  it('renders nothing when the transcript has no timestamps', () => {
    const { container } = render(<SubtitleDownloadButton entry={baseEntry} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('downloads the SRT with the server-provided filename', async () => {
    const blob = new Blob(['1\r\n']);
    downloadSubtitles.mockResolvedValue({ blob, filename: 'transcript_weekly.srt' });

    render(<SubtitleDownloadButton entry={timedEntry} />);
    fireEvent.click(screen.getByRole('button', { name: 'Download transcript as SRT subtitles' }));

    await waitFor(() => {
      expect(triggerBrowserDownload).toHaveBeenCalledWith(blob, 'transcript_weekly.srt');
    });
    expect(downloadSubtitles).toHaveBeenCalledWith('entry-1', 'srt');
    expect(screen.getByText('Download SRT')).toBeInTheDocument();
  });

  it('shows the server error when the download fails', async () => {
    const error = new AxiosError('Not found', '404', undefined, undefined, {
      status: 404,
      statusText: 'Not Found',
      headers: {},
      config: { headers: new AxiosHeaders() },
      data: { detail: 'Timestamps are not available for this entry' },
    });
    downloadSubtitles.mockRejectedValue(error);

    render(<SubtitleDownloadButton entry={timedEntry} variant="compact" />);
    fireEvent.click(screen.getByRole('button', { name: 'Download transcript as SRT subtitles' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Timestamps are not available for this entry',
    );
    expect(triggerBrowserDownload).not.toHaveBeenCalled();
    expect(screen.getByText('SRT')).toBeInTheDocument();
  });
});

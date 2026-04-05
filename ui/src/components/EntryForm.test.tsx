import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { EntryForm } from './EntryForm';

const { createFromTranscript, createFromUrl, uploadFile } = vi.hoisted(() => ({
  createFromTranscript: vi.fn(),
  createFromUrl: vi.fn(),
  uploadFile: vi.fn(),
}));

vi.mock('../services/api', () => ({
  entryApi: {
    createFromTranscript,
    createFromUrl,
    uploadFile,
  },
}));

describe('EntryForm transcript submission', () => {
  beforeEach(() => {
    createFromTranscript.mockReset();
    createFromUrl.mockReset();
    uploadFile.mockReset();
  });

  it('creates an entry from an existing transcript', async () => {
    const onEntryCreated = vi.fn();
    const onClose = vi.fn();

    createFromTranscript.mockResolvedValue({
      id: 'entry-transcript-1',
      title: 'Board sync',
      source_type: 'upload',
      status: 'READY',
      archived: false,
      transcript: 'Already transcribed content',
      created_at: '2026-04-04T00:00:00Z',
      updated_at: '2026-04-04T00:00:00Z',
    });

    render(
      <EntryForm
        onEntryCreated={onEntryCreated}
        onClose={onClose}
      />
    );

    fireEvent.click(screen.getByLabelText('Transcript'));
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Board sync' } });
    fireEvent.change(screen.getByLabelText(/Transcript text/i), {
      target: { value: 'Already transcribed content' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Create Entry' }));

    await waitFor(() => {
      expect(createFromTranscript).toHaveBeenCalledWith({
        title: 'Board sync',
        transcript: 'Already transcribed content',
      });
    });

    expect(onEntryCreated).toHaveBeenCalledWith(expect.objectContaining({
      id: 'entry-transcript-1',
      status: 'READY',
    }));
    expect(onClose).toHaveBeenCalled();
  });
});

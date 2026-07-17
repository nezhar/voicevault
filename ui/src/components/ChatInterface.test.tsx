import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { ChatInterface } from './ChatInterface';
import { ChatStreamEvent } from '../types';

const { getPromptTemplates, chatWithEntryStream } = vi.hoisted(() => ({
  getPromptTemplates: vi.fn(),
  chatWithEntryStream: vi.fn(),
}));

vi.mock('../services/api', () => ({
  entryApi: {
    getPromptTemplates,
    chatWithEntryStream,
  },
}));

const readyEntry = {
  id: 'entry-1',
  title: 'Quarterly Review',
  source_type: 'upload' as const,
  status: 'READY' as const,
  archived: false,
  has_audio: false,
  transcript: 'Transcript content',
  created_at: '2026-04-03T10:00:00Z',
  updated_at: '2026-04-03T10:00:00Z',
};

describe('ChatInterface prompt templates', () => {
  beforeEach(() => {
    getPromptTemplates.mockResolvedValue([
      {
        id: 'template-1',
        label: 'Action items',
        preview_text: 'Extract decisions and owners',
        body_markdown: '## Action Items\n- List action items',
        sort_order: 10,
        is_active: true,
        created_at: '2026-04-03T00:00:00Z',
        updated_at: '2026-04-03T00:00:00Z',
      },
    ]);
    chatWithEntryStream.mockImplementation(
      async (_id: string, _data: unknown, onEvent: (event: ChatStreamEvent) => void) => {
        onEvent({ type: 'progress', stage: 'map', done: 0, total: 3 });
        onEvent({ type: 'progress', stage: 'map', done: 3, total: 3 });
        onEvent({ type: 'progress', stage: 'reduce' });
        onEvent({ type: 'answer', content: 'Done' });
        onEvent({ type: 'done' });
      },
    );
  });

  it('supports preview, prefill, and immediate send for prompt templates', async () => {
    render(<ChatInterface entry={readyEntry} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Action items')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Preview Action items' }));
    expect(screen.getByText('Action Items')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Use Only Action items' }));
    await waitFor(() => {
      expect(screen.getByRole('textbox')).toHaveValue('## Action Items\n- List action items');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Use & Send Action items' }));

    await waitFor(() => {
      expect(chatWithEntryStream).toHaveBeenCalledWith(
        'entry-1',
        expect.objectContaining({
          message: '## Action Items\n- List action items',
        }),
        expect.any(Function),
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Done')).toBeInTheDocument();
    });
  });
});

describe('ChatInterface map-reduce progress', () => {
  beforeEach(() => {
    getPromptTemplates.mockResolvedValue([]);
  });

  it('shows the section counter while the map stage is running', async () => {
    let emit!: (event: ChatStreamEvent) => void;
    let finish!: () => void;
    chatWithEntryStream.mockImplementation(
      (_id: string, _data: unknown, onEvent: (event: ChatStreamEvent) => void) => {
        emit = onEvent;
        return new Promise<void>((resolve) => {
          finish = resolve;
        });
      },
    );

    render(<ChatInterface entry={readyEntry} onClose={vi.fn()} />);

    const textbox = screen.getByRole('textbox');
    fireEvent.change(textbox, {
      target: { value: 'What happened?' },
    });
    fireEvent.submit(textbox.closest('form')!);

    await waitFor(() => {
      expect(chatWithEntryStream).toHaveBeenCalled();
    });

    emit({ type: 'progress', stage: 'map', done: 1, total: 3 });
    await waitFor(() => {
      expect(screen.getByText('Analyzing sections… 1/3')).toBeInTheDocument();
    });

    emit({ type: 'progress', stage: 'reduce' });
    await waitFor(() => {
      expect(screen.getByText('Generating answer…')).toBeInTheDocument();
    });

    emit({ type: 'answer', content: 'Final answer' });
    finish();
    await waitFor(() => {
      expect(screen.getByText('Final answer')).toBeInTheDocument();
    });
  });
});

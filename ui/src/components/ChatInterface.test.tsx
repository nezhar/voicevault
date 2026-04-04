import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { ChatInterface } from './ChatInterface';

const { getPromptTemplates, chatWithEntry } = vi.hoisted(() => ({
  getPromptTemplates: vi.fn(),
  chatWithEntry: vi.fn(),
}));

vi.mock('../services/api', () => ({
  entryApi: {
    getPromptTemplates,
    chatWithEntry,
  },
}));

const readyEntry = {
  id: 'entry-1',
  title: 'Quarterly Review',
  source_type: 'upload' as const,
  status: 'READY' as const,
  archived: false,
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
    chatWithEntry.mockResolvedValue({
      message: 'Done',
      timestamp: '2026-04-03T10:00:00Z',
    });
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
      expect(chatWithEntry).toHaveBeenCalledWith('entry-1', expect.objectContaining({
        message: '## Action Items\n- List action items',
      }));
    });
  });
});

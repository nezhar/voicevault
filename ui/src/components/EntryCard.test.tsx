import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EntryCard } from './EntryCard';
import { Entry } from '../types';

const baseEntry: Entry = {
  id: 'entry-1',
  title: 'Quarterly Review',
  source_type: 'upload',
  status: 'READY',
  transcript: 'Transcript content',
  created_at: '2026-04-03T10:00:00Z',
  updated_at: '2026-04-03T10:00:00Z',
  archived: false,
};

describe('EntryCard archive actions', () => {
  it('shows archive for ready active entries', () => {
    render(
      <EntryCard
        entry={baseEntry}
        onOpenChat={vi.fn()}
        onDelete={vi.fn()}
        onToggleArchive={vi.fn()}
      />
    );

    expect(screen.getByRole('button', { name: 'Archive entry' })).toBeInTheDocument();
  });

  it('shows unarchive for archived entries', () => {
    render(
      <EntryCard
        entry={{ ...baseEntry, archived: true }}
        onOpenChat={vi.fn()}
        onDelete={vi.fn()}
        onToggleArchive={vi.fn()}
      />
    );

    expect(screen.getByRole('button', { name: 'Unarchive entry' })).toBeInTheDocument();
  });

  it('hides archive action for non-ready entries', () => {
    render(
      <EntryCard
        entry={{ ...baseEntry, status: 'IN_PROGRESS' }}
        onOpenChat={vi.fn()}
        onDelete={vi.fn()}
        onToggleArchive={vi.fn()}
      />
    );

    expect(screen.queryByRole('button', { name: 'Archive entry' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Unarchive entry' })).not.toBeInTheDocument();
  });
});

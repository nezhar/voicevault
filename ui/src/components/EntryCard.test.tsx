import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EntryCard } from './EntryCard';
import { Entry, Project } from '../types';

const OWNER_ID = 'me';

const baseEntry: Entry = {
  id: 'entry-1',
  title: 'Quarterly Review',
  source_type: 'upload',
  status: 'READY',
  transcript: 'Transcript content',
  created_at: '2026-04-03T10:00:00Z',
  updated_at: '2026-04-03T10:00:00Z',
  archived: false,
  has_audio: false,
  owner: { id: OWNER_ID, display_name: 'Me' },
};

const baseProject: Project = {
  id: 'p1',
  name: 'Team Alpha',
  description: null,
  created_by: 'u1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  my_role: 'viewer',
  member_count: 2,
  entry_count: 5,
};

const makeEntry = (overrides: Partial<Entry> = {}): Entry => ({ ...baseEntry, ...overrides });

const renderCard = (props: {
  entry?: Entry;
  projects?: Project[];
  currentUserId?: string;
  onMoveEntry?: (entry: Entry) => void;
}) =>
  render(
    <EntryCard
      entry={props.entry ?? baseEntry}
      projects={props.projects ?? []}
      currentUserId={props.currentUserId ?? OWNER_ID}
      onOpenChat={vi.fn()}
      onDelete={vi.fn()}
      onToggleArchive={vi.fn()}
      onEditMetadata={vi.fn()}
      onViewTimestamps={vi.fn()}
      onMoveEntry={props.onMoveEntry ?? vi.fn()}
    />,
  );

describe('EntryCard archive actions', () => {
  it('shows archive for ready active entries', () => {
    renderCard({});
    expect(screen.getByRole('button', { name: 'Archive entry' })).toBeInTheDocument();
  });

  it('shows unarchive for archived entries', () => {
    renderCard({ entry: makeEntry({ archived: true }) });
    expect(screen.getByRole('button', { name: 'Unarchive entry' })).toBeInTheDocument();
  });

  it('hides archive action for non-ready entries', () => {
    renderCard({ entry: makeEntry({ status: 'IN_PROGRESS' }) });
    expect(screen.queryByRole('button', { name: 'Archive entry' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Unarchive entry' })).not.toBeInTheDocument();
  });
});

describe('EntryCard project + permissions', () => {
  it('hides delete for non-owners and shows the project badge', () => {
    const entry = makeEntry({
      project_id: 'p1',
      owner: { id: 'other-user', display_name: 'Someone Else' },
    });
    const projects: Project[] = [
      { ...baseProject, id: 'p1', name: 'Team Alpha', my_role: 'viewer' },
    ];
    renderCard({ entry, projects, currentUserId: 'me' });

    expect(screen.getByText('Team Alpha')).toBeInTheDocument();
    expect(screen.queryByLabelText(/delete/i)).not.toBeInTheDocument();
  });
});

describe('move to project', () => {
  const editorProject: Project = {
    ...baseProject,
    id: 'p-editor',
    name: 'Editable',
    my_role: 'editor',
  };

  it('shows the move button for the entry owner only', () => {
    const { unmount } = renderCard({ projects: [editorProject] });
    expect(screen.getByLabelText('Move to project')).toBeInTheDocument();
    unmount();

    renderCard({ projects: [editorProject], currentUserId: 'someone-else' });
    expect(screen.queryByLabelText('Move to project')).not.toBeInTheDocument();
  });

  it('clicking the move button calls onMoveEntry with the entry', () => {
    const onMoveEntry = vi.fn();
    renderCard({ onMoveEntry });

    fireEvent.click(screen.getByLabelText('Move to project'));
    expect(onMoveEntry).toHaveBeenCalledWith(expect.objectContaining({ id: 'entry-1' }));
  });
});

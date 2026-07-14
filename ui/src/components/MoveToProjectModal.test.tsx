import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MoveToProjectModal } from './MoveToProjectModal';
import { Entry, Project } from '../types';

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
  owner: { id: 'me', display_name: 'Me' },
};

const baseProject: Project = {
  id: 'p1',
  name: 'Team Alpha',
  description: null,
  created_by: 'u1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  my_role: 'editor',
  member_count: 2,
  entry_count: 5,
};

const editorProject: Project = {
  ...baseProject,
  id: 'p-editor',
  name: 'Editable',
  my_role: 'editor',
};
const ownerProject: Project = { ...baseProject, id: 'p-owner', name: 'Owned', my_role: 'owner' };
const viewerProject: Project = {
  ...baseProject,
  id: 'p-viewer',
  name: 'ViewOnly',
  my_role: 'viewer',
};

const renderModal = (props: {
  entry?: Entry;
  projects?: Project[];
  onClose?: () => void;
  onMove?: (entry: Entry, projectId: string | null) => Promise<void>;
}) =>
  render(
    <MoveToProjectModal
      entry={props.entry ?? baseEntry}
      projects={props.projects ?? [editorProject, viewerProject]}
      isOpen
      onClose={props.onClose ?? vi.fn()}
      onMove={props.onMove ?? vi.fn().mockResolvedValue(undefined)}
    />,
  );

describe('MoveToProjectModal list contents', () => {
  it('lists Private plus editor+ projects and excludes viewer projects', () => {
    renderModal({ projects: [editorProject, ownerProject, viewerProject] });
    expect(screen.getByRole('button', { name: /Private \(only me\)/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Editable/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Owned/ })).toBeInTheDocument();
    expect(screen.queryByText('ViewOnly')).not.toBeInTheDocument();
  });

  it('filters projects by search while Private stays visible', () => {
    renderModal({ projects: [editorProject, ownerProject] });
    fireEvent.change(screen.getByLabelText('Search projects'), { target: { value: 'edit' } });
    expect(screen.getByRole('button', { name: /Editable/ })).toBeInTheDocument();
    expect(screen.queryByText('Owned')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Private \(only me\)/ })).toBeInTheDocument();
  });

  it('shows an empty message when no project matches the search', () => {
    renderModal({});
    fireEvent.change(screen.getByLabelText('Search projects'), { target: { value: 'zzz' } });
    expect(screen.getByText('No matching projects')).toBeInTheDocument();
  });
});

describe('MoveToProjectModal selection and confirm', () => {
  it('marks the current location and disables Move until the selection changes', () => {
    renderModal({
      entry: { ...baseEntry, project_id: 'p-editor' },
      projects: [editorProject],
    });
    expect(screen.getByRole('button', { name: /Editable.*current/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Move' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: /Private \(only me\)/ }));
    expect(screen.getByRole('button', { name: 'Move' })).toBeEnabled();
  });

  it('confirming a move to Private calls onMove with null and closes', async () => {
    const onMove = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    renderModal({
      entry: { ...baseEntry, project_id: 'p-editor' },
      projects: [editorProject],
      onMove,
      onClose,
    });

    fireEvent.click(screen.getByRole('button', { name: /Private \(only me\)/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Move' }));

    await waitFor(() =>
      expect(onMove).toHaveBeenCalledWith(expect.objectContaining({ id: 'entry-1' }), null),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('confirming a move into a project calls onMove with the project id', async () => {
    const onMove = vi.fn().mockResolvedValue(undefined);
    renderModal({ onMove });

    fireEvent.click(screen.getByRole('button', { name: /Editable/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Move' }));

    await waitFor(() =>
      expect(onMove).toHaveBeenCalledWith(expect.objectContaining({ id: 'entry-1' }), 'p-editor'),
    );
  });

  it('shows an inline error and stays open when the move fails', async () => {
    const onMove = vi.fn().mockRejectedValue(new Error('boom'));
    const onClose = vi.fn();
    renderModal({ onMove, onClose });

    fireEvent.click(screen.getByRole('button', { name: /Editable/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Move' }));

    expect(await screen.findByText('Failed to move entry. Please try again.')).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('closes on Escape without moving', () => {
    const onMove = vi.fn();
    const onClose = vi.fn();
    renderModal({ onMove, onClose });

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
    expect(onMove).not.toHaveBeenCalled();
  });
});

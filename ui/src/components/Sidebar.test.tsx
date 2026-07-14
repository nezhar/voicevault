import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { Sidebar } from './Sidebar';
import { Project } from '../types';

const project: Project = {
  id: 'p1',
  name: 'Team Alpha',
  description: null,
  created_by: 'u1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  my_role: 'owner',
  member_count: 2,
  entry_count: 5,
};

describe('Sidebar', () => {
  it('renders nav items and projects with role badge', () => {
    render(
      <Sidebar
        view={{ kind: 'all' }}
        projects={[project]}
        onSelectView={vi.fn()}
        onCreateProject={vi.fn()}
        onOpenSettings={vi.fn()}
      />,
    );
    expect(screen.getByText('All Entries')).toBeInTheDocument();
    expect(screen.getByText('My Entries')).toBeInTheDocument();
    expect(screen.getByText('Team Alpha')).toBeInTheDocument();
    expect(screen.getByText('owner')).toBeInTheDocument();
  });

  it('selects a project view on click', () => {
    const onSelectView = vi.fn();
    render(
      <Sidebar
        view={{ kind: 'all' }}
        projects={[project]}
        onSelectView={onSelectView}
        onCreateProject={vi.fn()}
        onOpenSettings={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText('Team Alpha'));
    expect(onSelectView).toHaveBeenCalledWith({ kind: 'project', projectId: 'p1' });
  });
});

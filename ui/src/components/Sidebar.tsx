import React from 'react';
import { FileText, User as UserIcon, Plus, Settings, FolderOpen } from 'lucide-react';
import { Project } from '../types';

export type EntryView = { kind: 'all' } | { kind: 'mine' } | { kind: 'project'; projectId: string };

interface SidebarProps {
  view: EntryView;
  projects: Project[];
  onSelectView: (view: EntryView) => void;
  onCreateProject: () => void;
  onOpenSettings: (project: Project) => void;
}

const itemClass = (active: boolean) =>
  `w-full flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
    active
      ? 'bg-primary-50 text-primary-700'
      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
  }`;

export const Sidebar: React.FC<SidebarProps> = ({
  view,
  projects,
  onSelectView,
  onCreateProject,
  onOpenSettings,
}) => {
  return (
    <nav className="flex h-full w-60 flex-col gap-1 border-r border-gray-200 bg-white p-3">
      <button
        onClick={() => onSelectView({ kind: 'all' })}
        className={itemClass(view.kind === 'all')}
      >
        <FileText className="h-4 w-4" />
        All Entries
      </button>
      <button
        onClick={() => onSelectView({ kind: 'mine' })}
        className={itemClass(view.kind === 'mine')}
      >
        <UserIcon className="h-4 w-4" />
        My Entries
      </button>

      <div className="mt-4 px-3 text-xs font-semibold uppercase tracking-wide text-gray-400">
        Projects
      </div>
      {projects.map((project) => {
        const active = view.kind === 'project' && view.projectId === project.id;
        return (
          <div key={project.id} className="group flex items-center">
            <button
              onClick={() => onSelectView({ kind: 'project', projectId: project.id })}
              className={`${itemClass(active)} flex-1 min-w-0`}
              title={project.name}
            >
              <FolderOpen className="h-4 w-4 shrink-0" />
              <span className="truncate">{project.name}</span>
              <span className="ml-auto rounded bg-gray-100 px-1.5 py-0.5 text-[10px] uppercase text-gray-500">
                {project.my_role}
              </span>
            </button>
            <button
              onClick={() => onOpenSettings(project)}
              className="ml-1 hidden rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700 group-hover:block"
              aria-label={`Settings for ${project.name}`}
            >
              <Settings className="h-4 w-4" />
            </button>
          </div>
        );
      })}

      <button
        onClick={onCreateProject}
        className="mt-1 flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-gray-500 hover:bg-gray-100 hover:text-gray-900"
      >
        <Plus className="h-4 w-4" />
        New Project
      </button>
    </nav>
  );
};

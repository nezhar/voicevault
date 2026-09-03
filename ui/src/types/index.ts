export type EntryStatus = 'NEW' | 'IN_PROGRESS' | 'READY' | 'COMPLETE' | 'ERROR';
export type SourceType = 'upload' | 'url';

export interface TranscriptWord {
  word: string;
  start: number;
  end: number;
}

export interface TranscriptSegment {
  text: string;
  start: number;
  end: number;
}

export interface Entry {
  id: string;
  title: string;
  source_type: SourceType;
  source_url?: string;
  filename?: string;
  status: EntryStatus;
  archived: boolean;
  has_audio: boolean;
  transcript?: string;
  transcript_words?: TranscriptWord[];
  transcript_segments?: TranscriptSegment[];
  summary?: string;
  speakers?: string;
  additional_context?: string;
  language?: string | null;
  error_message?: string;
  project_id?: string | null;
  owner?: { id: string; display_name: string } | null;
  created_at: string;
  updated_at: string;
}

export interface EntryMetadataUpdate {
  title?: string;
  speakers?: string;
  additional_context?: string;
  language?: string | null;
  language_set?: boolean;
  regenerate_transcript?: boolean;
}

export interface EntryCreate {
  title: string;
  source_url?: string;
  language?: string | null;
  project_id?: string | null;
}

export interface EntryTranscriptCreate {
  title: string;
  transcript: string;
  language?: string | null;
  project_id?: string | null;
}

export interface EntryList {
  entries: Entry[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

export interface ChatRequest {
  message: string;
  conversation_history?: ChatMessage[];
}

export interface ChatResponse {
  message: string;
  timestamp: string;
}

export interface ChatStreamEvent {
  type: 'progress' | 'answer' | 'done' | 'error';
  stage?: 'map' | 'reduce';
  done?: number;
  total?: number;
  content?: string;
  detail?: string;
}

export interface SummaryResponse {
  summary: string;
  timestamp: string;
}

export interface PromptTemplate {
  id: string;
  label: string;
  preview_text?: string;
  body_markdown: string;
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PromptTemplateCreate {
  label: string;
  preview_text?: string;
  body_markdown: string;
  sort_order?: number;
  is_active?: boolean;
}

export interface PromptTemplateUpdate {
  label?: string;
  preview_text?: string;
  body_markdown?: string;
  sort_order?: number;
  is_active?: boolean;
}

export type AuthMode = 'none' | 'token' | 'oidc';

export interface AuthConfig {
  mode: AuthMode;
}

export interface User {
  id: string;
  email: string;
  display_name: string;
}

export type ProjectRole = 'owner' | 'editor' | 'viewer';

export interface Project {
  id: string;
  name: string;
  description?: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  my_role: ProjectRole;
  member_count: number;
  entry_count: number;
  pending_request_count?: number;
}

export interface ProjectMember {
  user_id: string;
  email: string;
  display_name: string;
  role: ProjectRole;
}

export interface ProjectDetail extends Project {
  members: ProjectMember[];
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
}

export interface ProjectUpdate {
  name?: string;
  description?: string | null;
}

export type AccessRequestStatus = 'pending' | 'approved' | 'denied';

export interface ProjectOwner {
  display_name: string;
  email: string;
}

export interface ProjectPreview {
  id: string;
  name: string;
  owners: ProjectOwner[];
  my_role: ProjectRole | null;
  request_status: AccessRequestStatus | null;
  request_id: string | null;
  can_request: boolean;
}

export interface AccessRequest {
  id: string;
  project_id: string;
  user_id: string;
  email: string;
  display_name: string;
  status: AccessRequestStatus;
  message: string | null;
  created_at: string;
  decided_at: string | null;
  decided_by_name: string | null;
}

export const roleAtLeast = (role: ProjectRole | undefined, min: ProjectRole): boolean => {
  const order: Record<ProjectRole, number> = { viewer: 0, editor: 1, owner: 2 };
  return role !== undefined && order[role] >= order[min];
};

export interface EntryPermissions {
  canEdit: boolean;
  canDelete: boolean;
}

export const entryPermissions = (
  entry: Entry,
  userId: string | undefined,
  projects: Project[],
): EntryPermissions => {
  const isEntryOwner = !!userId && entry.owner?.id === userId;
  const projectRole = entry.project_id
    ? projects.find((p) => p.id === entry.project_id)?.my_role
    : undefined;
  return {
    canEdit: isEntryOwner || roleAtLeast(projectRole, 'editor'),
    canDelete: isEntryOwner,
  };
};

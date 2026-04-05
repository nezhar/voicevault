export type EntryStatus = 'NEW' | 'IN_PROGRESS' | 'READY' | 'COMPLETE' | 'ERROR';
export type SourceType = 'upload' | 'url';

export interface Entry {
  id: string;
  title: string;
  source_type: SourceType;
  source_url?: string;
  filename?: string;
  status: EntryStatus;
  archived: boolean;
  transcript?: string;
  summary?: string;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface EntryCreate {
  title: string;
  source_url?: string;
}

export interface EntryTranscriptCreate {
  title: string;
  transcript: string;
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

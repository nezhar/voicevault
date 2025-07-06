export type EntryStatus = 'NEW' | 'IN_PROGRESS' | 'READY' | 'COMPLETE' | 'ERROR';
export type SourceType = 'upload' | 'url';

export interface Entry {
  id: string;
  title: string;
  source_type: SourceType;
  source_url?: string;
  filename?: string;
  status: EntryStatus;
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

export interface EntryList {
  entries: Entry[];
  total: number;
  page: number;
  per_page: number;
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
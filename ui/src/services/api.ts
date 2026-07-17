import axios from 'axios';
import {
  Entry,
  EntryCreate,
  EntryTranscriptCreate,
  EntryList,
  EntryMetadataUpdate,
  ChatRequest,
  ChatStreamEvent,
  SummaryResponse,
  PromptTemplate,
  PromptTemplateCreate,
  PromptTemplateUpdate,
  AuthConfig,
  User,
  Project,
  ProjectDetail,
  ProjectMember,
  ProjectCreate,
  ProjectUpdate,
  ProjectRole,
} from '../types';

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor to include auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Add response interceptor to handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const url = error.config?.url ?? '';
      if (!url.includes('/auth/login') && !url.includes('/auth/me')) {
        localStorage.removeItem('auth_token');
        window.dispatchEvent(new Event('voicevault:unauthorized'));
      }
    }
    return Promise.reject(error);
  },
);

export const entryApi = {
  // Get all entries
  getEntries: async (
    page: number = 1,
    per_page: number = 12,
    search?: string,
    archived: boolean = false,
    projectId?: string, // UUID or the literal 'none' (private only)
    ownerOnly: boolean = false,
  ): Promise<EntryList> => {
    const params = new URLSearchParams({
      page: page.toString(),
      per_page: per_page.toString(),
      archived: String(archived),
    });
    if (search) params.append('search', search);
    if (projectId) params.append('project_id', projectId);
    if (ownerOnly) params.append('owner', 'me');
    const response = await api.get(`/entries/?${params.toString()}`);
    return response.data;
  },

  // Get single entry
  getEntry: async (id: string): Promise<Entry> => {
    const response = await api.get(`/entries/${id}`);
    return response.data;
  },

  // Create entry from URL
  createFromUrl: async (data: EntryCreate): Promise<Entry> => {
    const response = await api.post('/entries/url', data);
    return response.data;
  },

  // Upload file
  uploadFile: async (
    title: string,
    file: File,
    language?: string | null,
    projectId?: string | null,
  ): Promise<Entry> => {
    const formData = new FormData();
    formData.append('title', title);
    formData.append('file', file);
    if (language) {
      formData.append('language', language);
    }
    if (projectId) {
      formData.append('project_id', projectId);
    }

    const response = await api.post('/entries/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  // Move an entry into a project (or back to private with null)
  moveToProject: async (id: string, projectId: string | null): Promise<Entry> => {
    const response = await api.put(`/entries/${id}/project`, { project_id: projectId });
    return response.data;
  },

  // Create entry from transcript
  createFromTranscript: async (data: EntryTranscriptCreate): Promise<Entry> => {
    const response = await api.post('/entries/transcript', data);
    return response.data;
  },

  // Delete entry
  deleteEntry: async (id: string): Promise<void> => {
    await api.delete(`/entries/${id}`);
  },

  // Archive or unarchive entry
  setArchived: async (id: string, archived: boolean): Promise<Entry> => {
    const response = await api.put(`/entries/${id}/archive`, { archived });
    return response.data;
  },

  // Update custom metadata (speakers + additional context)
  updateMetadata: async (id: string, data: EntryMetadataUpdate): Promise<Entry> => {
    const response = await api.put(`/entries/${id}/metadata`, data);
    return response.data;
  },

  // Prompt templates
  getPromptTemplates: async (activeOnly: boolean = false): Promise<PromptTemplate[]> => {
    const response = await api.get('/prompt-templates/', {
      params: {
        active_only: activeOnly,
      },
    });
    return response.data;
  },

  createPromptTemplate: async (data: PromptTemplateCreate): Promise<PromptTemplate> => {
    const response = await api.post('/prompt-templates/', data);
    return response.data;
  },

  updatePromptTemplate: async (id: string, data: PromptTemplateUpdate): Promise<PromptTemplate> => {
    const response = await api.put(`/prompt-templates/${id}`, data);
    return response.data;
  },

  deletePromptTemplate: async (id: string): Promise<void> => {
    await api.delete(`/prompt-templates/${id}`);
  },

  // Chat with entry via SSE map-reduce stream. Uses fetch (not axios):
  // axios buffers the whole response, which defeats progress events.
  chatWithEntryStream: async (
    id: string,
    data: ChatRequest,
    onEvent: (event: ChatStreamEvent) => void,
  ): Promise<void> => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = localStorage.getItem('auth_token');
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetch(`/api/entries/${id}/chat`, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: JSON.stringify(data),
    });
    if (!response.ok || !response.body) {
      throw new Error(`Chat request failed with status ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let separator;
      while ((separator = buffer.indexOf('\n\n')) !== -1) {
        const rawEvent = buffer.slice(0, separator);
        buffer = buffer.slice(separator + 2);
        const dataLine = rawEvent.split('\n').find((line) => line.startsWith('data: '));
        if (dataLine) {
          onEvent(JSON.parse(dataLine.slice(6)) as ChatStreamEvent);
        }
      }
    }
  },

  // Generate summary
  generateSummary: async (id: string): Promise<SummaryResponse> => {
    const response = await api.post(`/entries/${id}/summary`);
    return response.data;
  },

  // Fetch the entry's audio as a Blob URL for playback in <audio>.
  // Returns both the URL (to set as src) and the Blob (in case the caller
  // wants to download). Caller is responsible for revoking the URL.
  getAudioBlobUrl: async (id: string): Promise<{ url: string; blob: Blob }> => {
    const response = await api.get(`/entries/${id}/audio`, {
      responseType: 'blob',
    });
    const blob = response.data as Blob;
    return { url: URL.createObjectURL(blob), blob };
  },
};

export const authApi = {
  login: async (token: string): Promise<{ message: string; token: string }> => {
    const response = await api.post('/auth/login', { token });
    return response.data;
  },

  verify: async (token: string): Promise<{ valid: boolean; message: string }> => {
    const response = await api.post('/auth/verify', { token });
    return response.data;
  },

  getConfig: async (): Promise<AuthConfig> => {
    const response = await api.get('/auth/config');
    return response.data;
  },

  me: async (): Promise<User> => {
    const response = await api.get('/auth/me');
    return response.data;
  },

  logout: async (): Promise<void> => {
    await api.post('/auth/logout');
  },
};

export const projectApi = {
  list: async (): Promise<Project[]> => {
    const response = await api.get('/projects/');
    return response.data;
  },

  get: async (id: string): Promise<ProjectDetail> => {
    const response = await api.get(`/projects/${id}`);
    return response.data;
  },

  create: async (data: ProjectCreate): Promise<Project> => {
    const response = await api.post('/projects/', data);
    return response.data;
  },

  update: async (id: string, data: ProjectUpdate): Promise<Project> => {
    const response = await api.put(`/projects/${id}`, data);
    return response.data;
  },

  remove: async (id: string): Promise<void> => {
    await api.delete(`/projects/${id}`);
  },

  addMember: async (id: string, email: string, role: ProjectRole): Promise<ProjectMember> => {
    const response = await api.post(`/projects/${id}/members`, { email, role });
    return response.data;
  },

  updateMember: async (id: string, userId: string, role: ProjectRole): Promise<ProjectMember> => {
    const response = await api.put(`/projects/${id}/members/${userId}`, { role });
    return response.data;
  },

  removeMember: async (id: string, userId: string): Promise<void> => {
    await api.delete(`/projects/${id}/members/${userId}`);
  },
};

// Auth helper functions
export const auth = {
  setToken: (token: string) => {
    localStorage.setItem('auth_token', token);
  },

  getToken: () => {
    return localStorage.getItem('auth_token');
  },

  removeToken: () => {
    localStorage.removeItem('auth_token');
  },

  isAuthenticated: () => {
    return !!localStorage.getItem('auth_token');
  },
};

export default api;

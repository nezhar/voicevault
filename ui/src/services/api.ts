import axios from 'axios';
import {
  Entry,
  EntryCreate,
  EntryTranscriptCreate,
  EntryList,
  ChatRequest,
  ChatResponse,
  SummaryResponse,
  PromptTemplate,
  PromptTemplateCreate,
  PromptTemplateUpdate,
} from '../types';

const api = axios.create({
  baseURL: '/api',
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
      // Only redirect if this is not a login attempt
      if (!error.config?.url?.includes('/auth/login')) {
        // Clear token and redirect to login
        localStorage.removeItem('auth_token');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export const entryApi = {
  // Get all entries
  getEntries: async (
    page: number = 1,
    per_page: number = 12,
    search?: string,
    archived: boolean = false
  ): Promise<EntryList> => {
    const params = new URLSearchParams({
      page: page.toString(),
      per_page: per_page.toString(),
      archived: String(archived),
    });
    if (search) {
      params.append('search', search);
    }
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
  uploadFile: async (title: string, file: File): Promise<Entry> => {
    const formData = new FormData();
    formData.append('title', title);
    formData.append('file', file);

    const response = await api.post('/entries/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
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

  // Chat with entry
  chatWithEntry: async (id: string, data: ChatRequest): Promise<ChatResponse> => {
    const response = await api.post(`/entries/${id}/chat`, data);
    return response.data;
  },

  // Generate summary
  generateSummary: async (id: string): Promise<SummaryResponse> => {
    const response = await api.post(`/entries/${id}/summary`);
    return response.data;
  },
};

export const authApi = {
  // Login with token
  login: async (token: string): Promise<{ message: string; token: string }> => {
    const response = await api.post('/auth/login', { token });
    return response.data;
  },

  // Verify token
  verify: async (token: string): Promise<{ valid: boolean; message: string }> => {
    const response = await api.post('/auth/verify', { token });
    return response.data;
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

import axios from 'axios';
import { Entry, EntryCreate, EntryList } from '../types';

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const entryApi = {
  // Get all entries
  getEntries: async (page: number = 1, per_page: number = 10): Promise<EntryList> => {
    const response = await api.get(`/entries/?page=${page}&per_page=${per_page}`);
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

  // Delete entry
  deleteEntry: async (id: string): Promise<void> => {
    await api.delete(`/entries/${id}`);
  },
};

export default api;
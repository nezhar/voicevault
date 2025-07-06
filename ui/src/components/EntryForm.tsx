import React, { useState } from 'react';
import { Upload, Link, Loader2 } from 'lucide-react';
import { entryApi } from '../services/api';
import { Entry } from '../types';

interface EntryFormProps {
  onEntryCreated: (entry: Entry) => void;
}

type SubmissionType = 'url' | 'upload';

export const EntryForm: React.FC<EntryFormProps> = ({ onEntryCreated }) => {
  const [submissionType, setSubmissionType] = useState<SubmissionType>('url');
  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      let entry: Entry;

      if (submissionType === 'url') {
        if (!url.trim()) {
          throw new Error('URL is required');
        }
        entry = await entryApi.createFromUrl({
          title: title.trim() || new URL(url).hostname,
          source_url: url.trim(),
        });
      } else {
        if (!file) {
          throw new Error('File is required');
        }
        entry = await entryApi.uploadFile(
          title.trim() || file.name,
          file
        );
      }

      onEntryCreated(entry);
      
      // Reset form
      setTitle('');
      setUrl('');
      setFile(null);
      
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'An error occurred');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      if (!title.trim()) {
        setTitle(selectedFile.name.replace(/\.[^/.]+$/, ''));
      }
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-6 max-w-2xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Add New Entry</h2>
      
      {/* Radio buttons for submission type */}
      <div className="mb-6">
        <div className="flex space-x-6">
          <label className="flex items-center">
            <input
              type="radio"
              value="url"
              checked={submissionType === 'url'}
              onChange={(e) => setSubmissionType(e.target.value as SubmissionType)}
              className="h-4 w-4 text-primary-600 border-gray-300 focus:ring-primary-500"
            />
            <Link className="ml-2 h-5 w-5 text-gray-500" />
            <span className="ml-2 text-sm font-medium text-gray-700">From URL</span>
          </label>
          
          <label className="flex items-center">
            <input
              type="radio"
              value="upload"
              checked={submissionType === 'upload'}
              onChange={(e) => setSubmissionType(e.target.value as SubmissionType)}
              className="h-4 w-4 text-primary-600 border-gray-300 focus:ring-primary-500"
            />
            <Upload className="ml-2 h-5 w-5 text-gray-500" />
            <span className="ml-2 text-sm font-medium text-gray-700">Upload File</span>
          </label>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Title field */}
        <div>
          <label htmlFor="title" className="block text-sm font-medium text-gray-700 mb-1">
            Title
          </label>
          <input
            type="text"
            id="title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Enter a title for your entry"
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
          />
        </div>

        {/* URL input (when URL is selected) */}
        {submissionType === 'url' && (
          <div>
            <label htmlFor="url" className="block text-sm font-medium text-gray-700 mb-1">
              URL <span className="text-red-500">*</span>
            </label>
            <input
              type="url"
              id="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://youtube.com/watch?v=..."
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500"
            />
            <p className="mt-1 text-sm text-gray-500">
              Supported: YouTube, Vimeo, SoundCloud
            </p>
          </div>
        )}

        {/* File upload (when upload is selected) */}
        {submissionType === 'upload' && (
          <div>
            <label htmlFor="file" className="block text-sm font-medium text-gray-700 mb-1">
              File <span className="text-red-500">*</span>
            </label>
            <div className="mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-gray-300 border-dashed rounded-md hover:border-primary-400 transition-colors">
              <div className="space-y-1 text-center">
                <Upload className="mx-auto h-12 w-12 text-gray-400" />
                <div className="flex text-sm text-gray-600">
                  <label
                    htmlFor="file"
                    className="relative cursor-pointer bg-white rounded-md font-medium text-primary-600 hover:text-primary-500 focus-within:outline-none focus-within:ring-2 focus-within:ring-offset-2 focus-within:ring-primary-500"
                  >
                    <span>Upload a file</span>
                    <input
                      id="file"
                      type="file"
                      className="sr-only"
                      accept="audio/*,video/*,.mp3,.wav,.m4a,.flac,.ogg,.opus,.mp4,.mpeg,.webm"
                      onChange={handleFileChange}
                      required
                    />
                  </label>
                  <p className="pl-1">or drag and drop</p>
                </div>
                <p className="text-xs text-gray-500">
                  MP3, WAV, M4A, FLAC, OGG, OPUS, MP4, MPEG, WEBM
                </p>
                {file && (
                  <p className="text-sm text-primary-600 font-medium">
                    Selected: {file.name}
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Error message */}
        {error && (
          <div className="p-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md">
            {error}
          </div>
        )}

        {/* Submit button */}
        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="animate-spin -ml-1 mr-3 h-5 w-5" />
              Processing...
            </>
          ) : (
            'Create Entry'
          )}
        </button>
      </form>
    </div>
  );
};
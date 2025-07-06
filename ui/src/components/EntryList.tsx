import React from 'react';
import { EntryCard } from './EntryCard';
import { Entry } from '../types';

interface EntryListProps {
  entries: Entry[];
  onRefresh: () => void;
  onOpenChat: (entry: Entry) => void;
  onDelete: (entry: Entry) => void;
}

export const EntryList: React.FC<EntryListProps> = ({ entries, onRefresh, onOpenChat, onDelete }) => {
  if (entries.length === 0) {
    return (
      <div className="text-center py-12">
        <div className="text-gray-500 text-lg mb-2">No entries yet</div>
        <div className="text-gray-400 text-sm">Create your first entry above</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold text-gray-900">Your Entries</h2>
        <button
          onClick={onRefresh}
          className="text-sm text-primary-600 hover:text-primary-500 font-medium"
        >
          Refresh
        </button>
      </div>
      
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {entries.map((entry) => (
          <EntryCard
            key={entry.id}
            entry={entry}
            onOpenChat={onOpenChat}
            onDelete={onDelete}
          />
        ))}
      </div>
    </div>
  );
};
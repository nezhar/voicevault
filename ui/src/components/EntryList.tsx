import React from 'react';
import { EntryCard } from './EntryCard';
import { Entry } from '../types';
import { Loader2 } from 'lucide-react';

interface EntryListProps {
  entries: Entry[];
  total: number;
  hasMore: boolean;
  isLoadingMore: boolean;
  isArchivedView: boolean;
  onRefresh: () => void;
  onOpenChat: (entry: Entry) => void;
  onDelete: (entry: Entry) => void;
  onToggleArchive: (entry: Entry, archived: boolean) => Promise<void>;
  onEditMetadata: (entry: Entry) => void;
  onViewTimestamps: (entry: Entry) => void;
  onLoadMore: () => void;
  isSearching?: boolean;
}

export const EntryList: React.FC<EntryListProps> = ({
  entries,
  total,
  hasMore,
  isLoadingMore,
  isArchivedView,
  onRefresh,
  onOpenChat,
  onDelete,
  onToggleArchive,
  onEditMetadata,
  onViewTimestamps,
  onLoadMore,
  isSearching = false,
}) => {
  if (entries.length === 0) {
    return (
      <div className="text-center py-12">
        <div className="text-gray-500 text-lg mb-2">
          {isSearching
            ? 'No results found'
            : isArchivedView
              ? 'No archived entries'
              : 'No entries yet'}
        </div>
        <div className="text-gray-400 text-sm">
          {isSearching
            ? 'Try a different search term'
            : isArchivedView
              ? 'Archive ready entries to find them here'
              : 'Use Add to create your first entry'}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">
            {isArchivedView ? 'Archived Entries' : 'Your Entries'}
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Showing {entries.length} of {total} {isArchivedView ? 'archived ' : ''}
            {total === 1 ? 'upload' : 'uploads'}
          </p>
        </div>
        <button
          onClick={onRefresh}
          className="min-h-11 self-start rounded-lg px-3 text-sm font-medium text-primary-600 hover:bg-primary-50 hover:text-primary-500 sm:self-auto"
        >
          Refresh
        </button>
      </div>

      <div className="grid gap-3 sm:gap-4 md:grid-cols-2 lg:grid-cols-3">
        {entries.map((entry) => (
          <EntryCard
            key={entry.id}
            entry={entry}
            onOpenChat={onOpenChat}
            onDelete={onDelete}
            onToggleArchive={onToggleArchive}
            onEditMetadata={onEditMetadata}
            onViewTimestamps={onViewTimestamps}
          />
        ))}
      </div>

      {/* Load More Button */}
      {hasMore && (
        <div className="flex justify-center pt-6">
          <button
            onClick={onLoadMore}
            disabled={isLoadingMore}
            className="flex min-h-11 w-full items-center justify-center gap-2 rounded-lg bg-primary-600 px-6 py-3 font-medium text-white transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:bg-gray-300 sm:w-auto"
          >
            {isLoadingMore ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                Loading...
              </>
            ) : (
              'Load More'
            )}
          </button>
        </div>
      )}
    </div>
  );
};

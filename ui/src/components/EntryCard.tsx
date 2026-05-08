import React, { useState } from 'react';
import { MessageCircle, Clock, CheckCircle, AlertCircle, Upload, Link, Trash2, Archive, RotateCcw, Tag } from 'lucide-react';
import { Entry, EntryStatus } from '../types';

interface EntryCardProps {
  entry: Entry;
  onOpenChat: (entry: Entry) => void;
  onDelete: (entry: Entry) => void;
  onToggleArchive: (entry: Entry, archived: boolean) => Promise<void>;
  onEditMetadata: (entry: Entry) => void;
}

const getStatusInfo = (status: EntryStatus) => {
  switch (status) {
    case 'NEW':
      return {
        label: 'Queued',
        color: 'text-blue-600 bg-blue-50 border-blue-200',
        icon: Clock,
      };
    case 'IN_PROGRESS':
      return {
        label: 'Processing',
        color: 'text-yellow-600 bg-yellow-50 border-yellow-200',
        icon: Clock,
      };
    case 'READY':
      return {
        label: 'Ready',
        color: 'text-green-600 bg-green-50 border-green-200',
        icon: CheckCircle,
      };
    case 'COMPLETE':
      return {
        label: 'Complete',
        color: 'text-green-600 bg-green-50 border-green-200',
        icon: CheckCircle,
      };
    case 'ERROR':
      return {
        label: 'Error',
        color: 'text-red-600 bg-red-50 border-red-200',
        icon: AlertCircle,
      };
    default:
      return {
        label: status,
        color: 'text-gray-600 bg-gray-50 border-gray-200',
        icon: Clock,
      };
  }
};

export const EntryCard: React.FC<EntryCardProps> = ({ entry, onOpenChat, onDelete, onToggleArchive, onEditMetadata }) => {
  const [isDeleting, setIsDeleting] = useState(false);
  const [isUpdatingArchive, setIsUpdatingArchive] = useState(false);
  const statusInfo = getStatusInfo(entry.status);
  const StatusIcon = statusInfo.icon;
  const canChat = entry.status === 'READY' && entry.transcript;
  const canToggleArchive = entry.status === 'READY';
  const hasMetadata = !!(entry.speakers || entry.additional_context);

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    
    if (!confirm(`Are you sure you want to delete "${entry.title}"? This action cannot be undone.`)) {
      return;
    }

    setIsDeleting(true);
    try {
      await onDelete(entry);
    } catch (error) {
      console.error('Failed to delete entry:', error);
      alert('Failed to delete entry. Please try again.');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleArchiveToggle = async (e: React.MouseEvent) => {
    e.stopPropagation();

    const message = entry.archived
      ? `Unarchive "${entry.title}"?`
      : `Archive "${entry.title}"? You can unarchive it later.`;
    if (!confirm(message)) {
      return;
    }

    setIsUpdatingArchive(true);
    try {
      await onToggleArchive(entry, !entry.archived);
    } catch (error) {
      console.error('Failed to update archive state:', error);
      alert('Failed to update archive state. Please try again.');
    } finally {
      setIsUpdatingArchive(false);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 hover:shadow-md transition-shadow flex">
      {/* Main content */}
      <div
        className={`flex-1 min-w-0 p-4 ${canChat ? 'cursor-pointer' : ''}`}
        onClick={canChat ? () => onOpenChat(entry) : undefined}
        onKeyDown={
          canChat
            ? (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onOpenChat(entry);
                }
              }
            : undefined
        }
        role={canChat ? 'button' : undefined}
        tabIndex={canChat ? 0 : undefined}
        aria-label={canChat ? `Open chat for ${entry.title}` : undefined}
      >
        {/* Header */}
        <div className="flex items-center space-x-2 mb-3">
          {entry.source_type === 'upload' ? (
            <Upload className="h-4 w-4 text-gray-400 flex-shrink-0" />
          ) : (
            <Link className="h-4 w-4 text-gray-400 flex-shrink-0" />
          )}
          <h3 className="font-medium text-gray-900 truncate" title={entry.title}>
            {entry.title}
          </h3>
        </div>

        {/* Status */}
        <div className="mb-3">
          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${statusInfo.color}`}>
            <StatusIcon className="h-3 w-3 mr-1" />
            {statusInfo.label}
          </span>
        </div>

        {/* Content preview */}
        {entry.transcript && (
          <div className="mb-3">
            <p className="text-sm text-gray-600 line-clamp-3">
              {entry.transcript.substring(0, 120)}
              {entry.transcript.length > 120 && '...'}
            </p>
          </div>
        )}

        {/* Status message */}
        {entry.error_message && (
          <div className={`mb-3 p-2 rounded text-sm ${
            entry.status === 'ERROR'
              ? 'bg-red-50 border border-red-200 text-red-600'
              : 'bg-blue-50 border border-blue-200 text-blue-600'
          }`}>
            {entry.error_message}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center pt-3 border-t border-gray-100">
          <span className="text-xs text-gray-500">
            {formatDate(entry.created_at)}
          </span>
        </div>
      </div>

      {/* Action rail */}
      <div className="flex flex-col items-center gap-1 py-3 px-2 border-l border-gray-100">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onEditMetadata(entry);
          }}
          className={`p-1 transition-colors hover:text-primary-600 ${
            hasMetadata ? 'text-primary-600' : 'text-gray-400'
          }`}
          title={hasMetadata ? 'Edit metadata (set)' : 'Add metadata'}
          aria-label="Edit entry metadata"
        >
          <Tag className="h-4 w-4" />
        </button>

        {canToggleArchive && (
          <button
            onClick={handleArchiveToggle}
            disabled={isUpdatingArchive}
            className="p-1 text-gray-400 hover:text-primary-600 transition-colors disabled:opacity-50"
            title={entry.archived ? 'Unarchive entry' : 'Archive entry'}
            aria-label={entry.archived ? 'Unarchive entry' : 'Archive entry'}
          >
            {entry.archived ? (
              <RotateCcw className="h-4 w-4" />
            ) : (
              <Archive className="h-4 w-4" />
            )}
          </button>
        )}

        <span className="block h-px w-4 bg-gray-200 my-1" aria-hidden="true" />

        <button
          onClick={handleDelete}
          disabled={isDeleting}
          className="p-1 text-gray-400 hover:text-red-600 transition-colors disabled:opacity-50"
          title="Delete entry"
          aria-label="Delete entry"
        >
          <Trash2 className="h-4 w-4" />
        </button>

        {canChat && (
          <button
            onClick={() => onOpenChat(entry)}
            className="mt-auto p-1.5 text-primary-600 bg-primary-50 border border-primary-200 rounded-md hover:bg-primary-100 transition-colors"
            title="Chat with transcript"
            aria-label="Chat with transcript"
          >
            <MessageCircle className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
};

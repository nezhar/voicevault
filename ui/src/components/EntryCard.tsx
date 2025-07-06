import React, { useState } from 'react';
import { MessageCircle, Clock, CheckCircle, AlertCircle, Upload, Link, Trash2 } from 'lucide-react';
import { Entry, EntryStatus } from '../types';

interface EntryCardProps {
  entry: Entry;
  onOpenChat: (entry: Entry) => void;
  onDelete: (entry: Entry) => void;
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

export const EntryCard: React.FC<EntryCardProps> = ({ entry, onOpenChat, onDelete }) => {
  const [isDeleting, setIsDeleting] = useState(false);
  const statusInfo = getStatusInfo(entry.status);
  const StatusIcon = statusInfo.icon;
  const canChat = entry.status === 'READY' && entry.transcript;

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

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center space-x-2 flex-1 min-w-0">
          {entry.source_type === 'upload' ? (
            <Upload className="h-4 w-4 text-gray-400 flex-shrink-0" />
          ) : (
            <Link className="h-4 w-4 text-gray-400 flex-shrink-0" />
          )}
          <h3 className="font-medium text-gray-900 truncate" title={entry.title}>
            {entry.title}
          </h3>
        </div>
        
        {/* Delete button */}
        <button
          onClick={handleDelete}
          disabled={isDeleting}
          className="flex-shrink-0 p-1 text-gray-400 hover:text-red-600 transition-colors disabled:opacity-50"
          title="Delete entry"
        >
          <Trash2 className="h-4 w-4" />
        </button>
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

      {/* Error message */}
      {entry.status === 'ERROR' && entry.error_message && (
        <div className="mb-3 p-2 bg-red-50 border border-red-200 rounded text-sm text-red-600">
          {entry.error_message}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-gray-100">
        <span className="text-xs text-gray-500">
          {formatDate(entry.created_at)}
        </span>
        
        {canChat && (
          <button
            onClick={() => onOpenChat(entry)}
            className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-primary-600 bg-primary-50 border border-primary-200 rounded-md hover:bg-primary-100 transition-colors"
          >
            <MessageCircle className="h-3 w-3 mr-1" />
            Chat
          </button>
        )}
      </div>
    </div>
  );
};
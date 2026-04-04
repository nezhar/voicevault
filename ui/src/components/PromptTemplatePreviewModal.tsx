import React from 'react';
import { X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

interface PromptTemplatePreviewModalProps {
  bodyMarkdown: string;
  isOpen: boolean;
  title: string;
  onClose: () => void;
}

export const PromptTemplatePreviewModal: React.FC<PromptTemplatePreviewModalProps> = ({
  bodyMarkdown,
  isOpen,
  title,
  onClose,
}) => {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-2xl rounded-xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
            <p className="text-sm text-gray-500">Rendered markdown preview</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
            aria-label="Close preview"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">
          <div className="prose prose-sm max-w-none">
            <ReactMarkdown>{bodyMarkdown}</ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  );
};

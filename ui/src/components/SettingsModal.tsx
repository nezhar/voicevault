import React, { useState } from 'react';
import { X } from 'lucide-react';

import { PromptTemplate, PromptTemplateCreate, PromptTemplateUpdate, SystemPrompt } from '../types';
import { PromptTemplateManager } from './PromptTemplateManager';
import { SystemPromptSettings } from './SystemPromptSettings';

type Tab = 'templates' | 'system-prompts';

interface SettingsModalProps {
  templates: PromptTemplate[];
  isOpen: boolean;
  isLoading: boolean;
  error: string | null;
  onClose: () => void;
  onCreate: (template: PromptTemplateCreate) => Promise<void> | void;
  onUpdate: (id: string, template: PromptTemplateUpdate) => Promise<void> | void;
  onDelete: (id: string) => Promise<void> | void;
  systemPrompts: SystemPrompt[];
  systemPromptsLoading: boolean;
  systemPromptsError: string | null;
  onUpdateSystemPrompt: (task: string, body: string) => Promise<void>;
  onResetSystemPrompt: (task: string) => Promise<void>;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  templates,
  isOpen,
  isLoading,
  error,
  onClose,
  onCreate,
  onUpdate,
  onDelete,
  systemPrompts,
  systemPromptsLoading,
  systemPromptsError,
  onUpdateSystemPrompt,
  onResetSystemPrompt,
}) => {
  const [activeTab, setActiveTab] = useState<Tab>('templates');

  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="relative flex h-[85vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Settings</h2>
          <button
            onClick={onClose}
            className="rounded-md p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
            aria-label="Close settings"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex border-b border-gray-200 px-6">
          <button
            className={`mr-4 border-b-2 py-3 text-sm font-medium transition-colors ${
              activeTab === 'templates'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
            onClick={() => setActiveTab('templates')}
          >
            Templates
          </button>
          <button
            className={`border-b-2 py-3 text-sm font-medium transition-colors ${
              activeTab === 'system-prompts'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
            onClick={() => setActiveTab('system-prompts')}
          >
            System Prompts
          </button>
        </div>

        <div className={`flex-1 overflow-auto ${activeTab === 'templates' ? '' : 'hidden'}`}>
          <PromptTemplateManager
            embedded
            templates={templates}
            isOpen={isOpen}
            isLoading={isLoading}
            error={error}
            onClose={onClose}
            onCreate={onCreate}
            onUpdate={onUpdate}
            onDelete={onDelete}
          />
        </div>
        <div className={`flex-1 overflow-auto ${activeTab === 'system-prompts' ? '' : 'hidden'}`}>
          <SystemPromptSettings
            prompts={systemPrompts}
            isLoading={systemPromptsLoading}
            error={systemPromptsError}
            onUpdate={onUpdateSystemPrompt}
            onReset={onResetSystemPrompt}
          />
        </div>
      </div>
    </div>
  );
};

import React, { useEffect, useState } from 'react';

import { SystemPrompt } from '../types';

const TASK_LABELS: Record<string, string> = {
  chat: 'Chat',
  summary: 'Summary',
};

const TASK_DESCRIPTIONS: Record<string, string> = {
  chat: 'System prompt sent to the AI when a user chats with a transcript. Use {entry_title} and {transcript} as placeholders.',
  summary: 'System prompt sent to the AI when generating a transcript summary. The transcript is appended automatically.',
};

interface SystemPromptSettingsProps {
  prompts: SystemPrompt[];
  isLoading: boolean;
  error: string | null;
  onUpdate: (task: string, body: string) => Promise<void>;
  onReset: (task: string) => Promise<void>;
}

interface CardState {
  body: string;
  dirty: boolean;
  saving: boolean;
  saveError: string | null;
}

export const SystemPromptSettings: React.FC<SystemPromptSettingsProps> = ({
  prompts,
  isLoading,
  error,
  onUpdate,
  onReset,
}) => {
  const [cardStates, setCardStates] = useState<Record<string, CardState>>({});

  useEffect(() => {
    const initial: Record<string, CardState> = {};
    for (const prompt of prompts) {
      initial[prompt.task] = {
        body: prompt.body,
        dirty: false,
        saving: false,
        saveError: null,
      };
    }
    setCardStates(initial);
  }, [prompts]);

  const handleChange = (task: string, value: string) => {
    setCardStates((prev) => ({
      ...prev,
      [task]: { ...prev[task], body: value, dirty: true, saveError: null },
    }));
  };

  const handleSave = async (task: string) => {
    const body = cardStates[task]?.body ?? '';
    setCardStates((prev) => ({
      ...prev,
      [task]: { ...prev[task], saving: true, saveError: null },
    }));

    try {
      await onUpdate(task, body);
      setCardStates((prev) => ({
        ...prev,
        [task]: { ...prev[task], saving: false, dirty: false },
      }));
    } catch {
      setCardStates((prev) => ({
        ...prev,
        [task]: {
          ...prev[task],
          saving: false,
          saveError: 'Failed to save. Please try again.',
        },
      }));
    }
  };

  const handleReset = async (task: string) => {
    if (!window.confirm('Reset this prompt to its default? Your edits will be lost.')) {
      return;
    }

    setCardStates((prev) => ({
      ...prev,
      [task]: { ...prev[task], saving: true, saveError: null },
    }));

    try {
      await onReset(task);
    } finally {
      setCardStates((prev) => ({
        ...prev,
        [task]: { ...prev[task], saving: false, dirty: false },
      }));
    }
  };

  if (isLoading) {
    return <div className="p-6 text-sm text-gray-500">Loading system prompts...</div>;
  }

  if (error) {
    return <div className="p-6 text-sm text-red-600">{error}</div>;
  }

  const tasks = ['chat', 'summary'];

  return (
    <div className="flex flex-col gap-4 p-6">
      {tasks.map((task) => {
        const state = cardStates[task];
        if (!state) {
          return null;
        }

        return (
          <div key={task} className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="mb-1 text-sm font-semibold text-gray-800">{TASK_LABELS[task]}</div>
            <div className="mb-3 text-xs text-gray-500">{TASK_DESCRIPTIONS[task]}</div>
            <textarea
              className="w-full rounded border border-gray-300 p-2 font-mono text-xs leading-relaxed focus:outline-none focus:ring-2 focus:ring-blue-500"
              rows={8}
              value={state.body}
              onChange={(event) => handleChange(task, event.target.value)}
            />
            {state.saveError && <div className="mt-1 text-xs text-red-600">{state.saveError}</div>}
            <div className="mt-3 flex gap-2">
              <button
                className="rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                disabled={!state.dirty || state.saving}
                onClick={() => handleSave(task)}
              >
                {state.saving ? 'Saving...' : 'Save'}
              </button>
              <button
                className="rounded border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                disabled={state.saving}
                onClick={() => handleReset(task)}
              >
                Reset to default
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
};

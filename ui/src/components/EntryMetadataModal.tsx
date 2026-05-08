import React, { Fragment, useEffect, useState } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { Loader2, X } from 'lucide-react';
import { entryApi } from '../services/api';
import { Entry } from '../types';

const TITLE_MAX = 255;
const SPEAKERS_MAX = 2000;
const ADDITIONAL_CONTEXT_MAX = 5000;

interface EntryMetadataModalProps {
  entry: Entry;
  isOpen: boolean;
  onClose: () => void;
  onSaved: (entry: Entry) => void;
}

export const EntryMetadataModal: React.FC<EntryMetadataModalProps> = ({
  entry,
  isOpen,
  onClose,
  onSaved,
}) => {
  const [title, setTitle] = useState(entry.title);
  const [speakers, setSpeakers] = useState(entry.speakers ?? '');
  const [additionalContext, setAdditionalContext] = useState(entry.additional_context ?? '');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setTitle(entry.title);
      setSpeakers(entry.speakers ?? '');
      setAdditionalContext(entry.additional_context ?? '');
      setError(null);
    }
  }, [isOpen, entry]);

  const trimmedTitle = title.trim();
  const trimmedSpeakers = speakers.trim();
  const trimmedContext = additionalContext.trim();
  const titleEmpty = trimmedTitle.length === 0;
  const titleOverLimit = title.length > TITLE_MAX;
  const speakersOverLimit = speakers.length > SPEAKERS_MAX;
  const contextOverLimit = additionalContext.length > ADDITIONAL_CONTEXT_MAX;
  const canSubmit =
    !titleEmpty && !titleOverLimit && !speakersOverLimit && !contextOverLimit && !isSaving;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (titleEmpty) {
      setError('Title cannot be empty.');
      return;
    }

    if (titleOverLimit || speakersOverLimit || contextOverLimit) {
      setError('One of the fields exceeds its maximum length.');
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      const updated = await entryApi.updateMetadata(entry.id, {
        title: trimmedTitle,
        speakers: trimmedSpeakers || undefined,
        additional_context: trimmedContext || undefined,
      });
      onSaved(updated);
      onClose();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to save metadata.';
      setError(message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Transition show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={isSaving ? () => undefined : onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-150"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-100"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/50" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-150"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-100"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-2xl rounded-xl bg-white shadow-2xl">
                <div className="flex items-start justify-between border-b border-gray-200 px-5 py-4">
                  <Dialog.Title className="text-lg font-semibold text-gray-900">
                    Edit entry details
                  </Dialog.Title>
                  <button
                    type="button"
                    onClick={onClose}
                    disabled={isSaving}
                    className="ml-3 rounded-md p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 disabled:opacity-50"
                    aria-label="Close metadata editor"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                <form onSubmit={handleSubmit}>
                  <div className="space-y-5 px-5 py-4">
                    <p className="text-sm text-gray-600">
                      Speakers and additional context are forwarded to the AI as part of the system
                      prompt during chats and summaries.
                    </p>

                    <div>
                      <label
                        htmlFor="entry-title"
                        className="block text-sm font-medium text-gray-700"
                      >
                        Title
                      </label>
                      <input
                        id="entry-title"
                        type="text"
                        value={title}
                        onChange={(event) => setTitle(event.target.value)}
                        maxLength={TITLE_MAX + 100}
                        className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                      />
                      <div className="mt-1 flex items-center justify-between text-xs">
                        <span className={titleEmpty ? 'font-medium text-red-600' : 'text-gray-500'}>
                          {titleEmpty ? 'Title is required.' : 'The display name for this entry.'}
                        </span>
                        <span
                          className={
                            titleOverLimit ? 'font-medium text-red-600' : 'text-gray-400'
                          }
                        >
                          {title.length}/{TITLE_MAX}
                        </span>
                      </div>
                    </div>

                    <div>
                      <label
                        htmlFor="entry-speakers"
                        className="block text-sm font-medium text-gray-700"
                      >
                        Speakers
                      </label>
                      <textarea
                        id="entry-speakers"
                        value={speakers}
                        onChange={(event) => setSpeakers(event.target.value)}
                        placeholder="e.g. Alice (host), Bob (guest engineer)"
                        rows={3}
                        maxLength={SPEAKERS_MAX + 100}
                        className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                      />
                      <div className="mt-1 flex items-center justify-between text-xs">
                        <span className="text-gray-500">
                          List the people on the recording, one per line or comma-separated.
                        </span>
                        <span
                          className={
                            speakersOverLimit ? 'font-medium text-red-600' : 'text-gray-400'
                          }
                        >
                          {speakers.length}/{SPEAKERS_MAX}
                        </span>
                      </div>
                    </div>

                    <div>
                      <label
                        htmlFor="entry-additional-context"
                        className="block text-sm font-medium text-gray-700"
                      >
                        Additional context
                      </label>
                      <textarea
                        id="entry-additional-context"
                        value={additionalContext}
                        onChange={(event) => setAdditionalContext(event.target.value)}
                        placeholder="Any background that helps the AI understand this recording — meeting agenda, jargon, project name, etc."
                        rows={6}
                        maxLength={ADDITIONAL_CONTEXT_MAX + 100}
                        className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                      />
                      <div className="mt-1 flex items-center justify-between text-xs">
                        <span className="text-gray-500">
                          Plain text. Markdown is fine but not rendered.
                        </span>
                        <span
                          className={
                            contextOverLimit ? 'font-medium text-red-600' : 'text-gray-400'
                          }
                        >
                          {additionalContext.length}/{ADDITIONAL_CONTEXT_MAX}
                        </span>
                      </div>
                    </div>

                    {error && (
                      <div
                        role="alert"
                        className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
                      >
                        {error}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-5 py-4">
                    <button
                      type="button"
                      onClick={onClose}
                      disabled={isSaving}
                      className="inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={!canSubmit}
                      className="inline-flex items-center gap-2 rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {isSaving && <Loader2 className="h-4 w-4 animate-spin" />}
                      Save changes
                    </button>
                  </div>
                </form>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
};

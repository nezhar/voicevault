import React, { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { AlertCircle, Loader2, Lock, Unlock, X } from 'lucide-react';
import { entryApi } from '../services/api';
import { Entry, TranscriptSegment, TranscriptWord } from '../types';

interface TranscriptTimestampModalProps {
  entry: Entry;
  isOpen: boolean;
  onClose: () => void;
}

type TranscriptLineKind = 'word' | 'segment';

interface TranscriptLine {
  start: number;
  end: number;
  kind: TranscriptLineKind;
  // Populated for kind === 'word'
  words?: TranscriptWord[];
  // Populated for kind === 'segment'
  text?: string;
}

// Whisper word streams have no segment breaks, so we group on long pauses,
// sentence-ending punctuation, and a time/word ceiling — whichever hits first.
const LINE_PAUSE_SECONDS = 0.6;
const LINE_MAX_DURATION_SECONDS = 10;
const LINE_MAX_WORDS = 18;
const SENTENCE_END = /[.!?…]["')\]]?$/;

// Window during which scroll events triggered by our own scrollIntoView call
// should be ignored — anything later is a real user interaction.
const PROGRAMMATIC_SCROLL_GRACE_MS = 250;

const formatTimestamp = (seconds: number): string => {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00';
  const totalSeconds = Math.floor(seconds);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  const mm = String(minutes).padStart(2, '0');
  const ss = String(secs).padStart(2, '0');
  return hours > 0 ? `${String(hours).padStart(2, '0')}:${mm}:${ss}` : `${mm}:${ss}`;
};

const groupWordsIntoLines = (words: TranscriptWord[]): TranscriptLine[] => {
  if (!words.length) return [];

  const lines: TranscriptLine[] = [];
  let current: TranscriptWord[] = [];
  let lineStart = words[0].start;

  const flush = () => {
    if (current.length) {
      lines.push({
        start: lineStart,
        end: current[current.length - 1].end,
        kind: 'word',
        words: current,
      });
      current = [];
    }
  };

  for (let i = 0; i < words.length; i++) {
    const word = words[i];
    const previous = current[current.length - 1];

    if (!previous) {
      lineStart = word.start;
      current.push(word);
      continue;
    }

    const gap = word.start - previous.end;
    const lineDuration = previous.end - lineStart;
    const sentenceBreak = SENTENCE_END.test(previous.word.trim());

    if (
      gap >= LINE_PAUSE_SECONDS ||
      sentenceBreak ||
      lineDuration >= LINE_MAX_DURATION_SECONDS ||
      current.length >= LINE_MAX_WORDS
    ) {
      flush();
      lineStart = word.start;
    }

    current.push(word);
  }

  flush();
  return lines;
};

const segmentsToLines = (segments: TranscriptSegment[]): TranscriptLine[] =>
  segments
    .filter((s) => s.text && s.text.trim().length > 0)
    .map((segment) => ({
      start: segment.start,
      end: segment.end,
      kind: 'segment' as const,
      text: segment.text,
    }));

// Locate the line containing a given audio time. Words have small gaps, so a
// linear scan with "last line whose start ≤ time" is robust and cheap.
const findActiveLineIndex = (lines: TranscriptLine[], time: number): number => {
  if (!lines.length || time < lines[0].start) return -1;
  let lo = 0;
  let hi = lines.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (lines[mid].start <= time) lo = mid;
    else hi = mid - 1;
  }
  return lo;
};

export const TranscriptTimestampModal: React.FC<TranscriptTimestampModalProps> = ({
  entry,
  isOpen,
  onClose,
}) => {
  const lines = useMemo<TranscriptLine[]>(() => {
    if (entry.transcript_words && entry.transcript_words.length > 0) {
      return groupWordsIntoLines(entry.transcript_words);
    }
    if (entry.transcript_segments && entry.transcript_segments.length > 0) {
      return segmentsToLines(entry.transcript_segments);
    }
    return [];
  }, [entry.transcript_words, entry.transcript_segments]);

  const hasLines = lines.length > 0;
  const hasPlainTranscript = !hasLines && !!entry.transcript && entry.transcript.trim().length > 0;
  const hasNothing = !hasLines && !hasPlainTranscript;

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const lineRefs = useRef<Array<HTMLDivElement | null>>([]);
  const programmaticScrollUntilRef = useRef(0);

  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [isLoadingAudio, setIsLoadingAudio] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [autoScroll, setAutoScroll] = useState(true);

  const activeLineIndex = useMemo(
    () => findActiveLineIndex(lines, currentTime),
    [lines, currentTime],
  );

  // Load the audio blob when the modal opens. Skip the request entirely if the
  // entry has no audio attached yet.
  useEffect(() => {
    if (!isOpen) return;

    setAudioUrl(null);
    setAudioError(null);
    setCurrentTime(0);
    setAutoScroll(true);

    if (!entry.has_audio) {
      setIsLoadingAudio(false);
      return;
    }

    let cancelled = false;
    let createdUrl: string | null = null;
    setIsLoadingAudio(true);

    (async () => {
      try {
        const { url } = await entryApi.getAudioBlobUrl(entry.id);
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        createdUrl = url;
        setAudioUrl(url);
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : 'Failed to load audio.';
        setAudioError(message);
      } finally {
        if (!cancelled) setIsLoadingAudio(false);
      }
    })();

    return () => {
      cancelled = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [isOpen, entry.id, entry.has_audio]);

  // Reset line refs when the line set changes so we don't keep stale entries.
  useEffect(() => {
    lineRefs.current = new Array(lines.length).fill(null);
  }, [lines.length]);

  // Auto-scroll the active line into view when it changes — but only when the
  // user hasn't taken over scrolling (autoScroll === true).
  useEffect(() => {
    if (!autoScroll) return;
    if (activeLineIndex < 0) return;
    const el = lineRefs.current[activeLineIndex];
    if (!el) return;
    programmaticScrollUntilRef.current = Date.now() + PROGRAMMATIC_SCROLL_GRACE_MS;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [activeLineIndex, autoScroll]);

  const handleTranscriptScroll = useCallback(() => {
    if (!autoScroll) return;
    if (Date.now() < programmaticScrollUntilRef.current) return;
    setAutoScroll(false);
  }, [autoScroll]);

  const handleTimeUpdate = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    setCurrentTime(audio.currentTime);
  }, []);

  const handleSeekTo = useCallback((time: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = time;
    setCurrentTime(time);
    // A user-initiated seek is an intentional jump; re-enable auto-follow so
    // the transcript snaps to the new position.
    setAutoScroll(true);
    if (audio.paused) {
      void audio.play().catch(() => {
        /* autoplay may be blocked — that's fine, user will hit play */
      });
    }
  }, []);

  const handleToggleAutoScroll = useCallback(() => {
    setAutoScroll((prev) => {
      const next = !prev;
      if (next && activeLineIndex >= 0) {
        // Re-enabling: snap immediately to the active line.
        const el = lineRefs.current[activeLineIndex];
        if (el) {
          programmaticScrollUntilRef.current = Date.now() + PROGRAMMATIC_SCROLL_GRACE_MS;
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }
      return next;
    });
  }, [activeLineIndex]);

  const transcriptStats = (() => {
    if (entry.transcript_words && entry.transcript_words.length > 0) {
      return `${entry.transcript_words.length.toLocaleString()} words`;
    }
    if (entry.transcript_segments && entry.transcript_segments.length > 0) {
      return `${entry.transcript_segments.length.toLocaleString()} segments`;
    }
    return null;
  })();

  return (
    <Transition show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
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
              <Dialog.Panel className="flex w-full max-w-3xl max-h-[85vh] flex-col rounded-xl bg-white shadow-2xl">
                <div className="flex items-start justify-between border-b border-gray-200 px-5 py-4">
                  <div className="min-w-0">
                    <Dialog.Title className="text-lg font-semibold text-gray-900">
                      Audio player
                    </Dialog.Title>
                    <p className="mt-0.5 truncate text-sm text-gray-500" title={entry.title}>
                      {entry.title}
                      {transcriptStats && (
                        <span className="ml-2 text-gray-400">• {transcriptStats}</span>
                      )}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={onClose}
                    className="ml-3 rounded-md p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                    aria-label="Close audio player"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                <div className="flex flex-col gap-3 border-b border-gray-200 bg-gray-50 px-5 py-3">
                  {!entry.has_audio ? (
                    <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
                      <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                      <span>Audio is not available for this entry yet.</span>
                    </div>
                  ) : audioError ? (
                    <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                      <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                      <span>{audioError}</span>
                    </div>
                  ) : isLoadingAudio && !audioUrl ? (
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Loading audio…
                    </div>
                  ) : (
                    <audio
                      ref={audioRef}
                      src={audioUrl ?? undefined}
                      controls
                      preload="auto"
                      onTimeUpdate={handleTimeUpdate}
                      onSeeked={handleTimeUpdate}
                      className="w-full"
                    />
                  )}

                  {hasLines && (
                    <div className="flex items-center justify-between gap-3">
                      <button
                        type="button"
                        onClick={handleToggleAutoScroll}
                        className={`inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
                          autoScroll
                            ? 'border-primary-200 bg-primary-50 text-primary-700 hover:bg-primary-100'
                            : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                        }`}
                        aria-pressed={autoScroll}
                        title={
                          autoScroll
                            ? 'Auto-scroll is following audio. It turns off when you scroll manually.'
                            : 'Auto-scroll is paused. Click to follow audio again.'
                        }
                      >
                        {autoScroll ? <Lock className="h-4 w-4" /> : <Unlock className="h-4 w-4" />}
                        Auto-scroll: {autoScroll ? 'on' : 'off'}
                      </button>
                      <span className="text-xs text-gray-500">
                        Click [time] to jump
                        {lines[0]?.kind === 'word' && ' • hover a word for exact range'}
                      </span>
                    </div>
                  )}
                </div>

                <div
                  onScroll={handleTranscriptScroll}
                  className="flex-1 overflow-y-auto px-5 py-4"
                >
                  {hasLines ? (
                    <div className="space-y-1 text-sm leading-relaxed text-gray-800">
                      {lines.map((line, index) => {
                        const isActive = index === activeLineIndex;
                        return (
                          <div
                            key={index}
                            ref={(el) => {
                              lineRefs.current[index] = el;
                            }}
                            className={`flex gap-3 rounded-md px-2 py-1 transition-colors ${
                              isActive ? 'bg-primary-50 ring-1 ring-primary-200' : ''
                            }`}
                          >
                            <button
                              type="button"
                              onClick={() => handleSeekTo(line.start)}
                              disabled={!audioUrl}
                              className="select-none whitespace-nowrap pt-0.5 font-mono text-xs font-semibold text-primary-600 tabular-nums hover:underline disabled:cursor-not-allowed disabled:no-underline disabled:opacity-50"
                              title={`Jump to ${formatTimestamp(line.start)}`}
                              aria-label={`Jump to ${formatTimestamp(line.start)}`}
                            >
                              [{formatTimestamp(line.start)}]
                            </button>
                            {line.kind === 'word' && line.words ? (
                              <p className="flex-1 whitespace-pre-wrap break-words">
                                {line.words.map((word, wordIndex) => {
                                  const wordIsActive =
                                    isActive &&
                                    currentTime >= word.start &&
                                    currentTime <= word.end;
                                  return (
                                    <span
                                      key={wordIndex}
                                      title={`${word.start.toFixed(3)}s – ${word.end.toFixed(3)}s`}
                                      className={`cursor-help ${
                                        wordIsActive ? 'font-semibold text-primary-700' : ''
                                      }`}
                                    >
                                      {wordIndex > 0 ? ' ' : ''}
                                      {word.word}
                                    </span>
                                  );
                                })}
                              </p>
                            ) : (
                              <p className="flex-1 whitespace-pre-wrap break-words">
                                {line.text}
                              </p>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : hasPlainTranscript ? (
                    <div className="space-y-3">
                      <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
                        Timestamps aren't available for this transcript — only the text is shown
                        below.
                      </div>
                      <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-gray-800">
                        {entry.transcript}
                      </p>
                    </div>
                  ) : (
                    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-700">
                      {hasNothing && entry.has_audio
                        ? 'No transcript is available for this entry yet. You can still play the audio above.'
                        : 'No transcript is available for this entry.'}
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-end border-t border-gray-200 px-5 py-3">
                  <button
                    type="button"
                    onClick={onClose}
                    className="inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
                  >
                    Close
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
};

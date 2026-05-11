import React, { useEffect, useMemo, useState } from 'react';

// ISO 639-1 codes Whisper understands. Auto is represented as null.
const CURATED_LANGUAGES: { code: string; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'de', label: 'German' },
  { code: 'es', label: 'Spanish' },
  { code: 'fr', label: 'French' },
  { code: 'it', label: 'Italian' },
  { code: 'nl', label: 'Dutch' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'pl', label: 'Polish' },
  { code: 'ru', label: 'Russian' },
  { code: 'tr', label: 'Turkish' },
  { code: 'ar', label: 'Arabic' },
  { code: 'hi', label: 'Hindi' },
  { code: 'zh', label: 'Chinese' },
  { code: 'ja', label: 'Japanese' },
  { code: 'ko', label: 'Korean' },
];

const CURATED_CODES = new Set(CURATED_LANGUAGES.map((entry) => entry.code));
const OTHER_VALUE = '__other__';
const AUTO_VALUE = '__auto__';

interface LanguageSelectProps {
  id?: string;
  value: string | null | undefined;
  onChange: (value: string | null) => void;
  disabled?: boolean;
  className?: string;
}

const normalize = (value: string | null | undefined): string | null => {
  if (!value) return null;
  const cleaned = value.trim().toLowerCase();
  if (!cleaned || cleaned === 'auto') return null;
  return cleaned;
};

export const LanguageSelect: React.FC<LanguageSelectProps> = ({
  id,
  value,
  onChange,
  disabled,
  className,
}) => {
  const normalized = useMemo(() => normalize(value), [value]);
  const startsAsCustom = normalized !== null && !CURATED_CODES.has(normalized);
  const [isCustom, setIsCustom] = useState(startsAsCustom);
  const [customDraft, setCustomDraft] = useState(startsAsCustom ? (normalized ?? '') : '');

  // Re-sync local state when an external value change moves us in or out of "custom".
  useEffect(() => {
    if (normalized === null) {
      setIsCustom(false);
      setCustomDraft('');
    } else if (CURATED_CODES.has(normalized)) {
      setIsCustom(false);
    } else {
      setIsCustom(true);
      setCustomDraft(normalized);
    }
  }, [normalized]);

  const selectValue = isCustom ? OTHER_VALUE : (normalized ?? AUTO_VALUE);

  const handleSelectChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const next = event.target.value;
    if (next === AUTO_VALUE) {
      setIsCustom(false);
      setCustomDraft('');
      onChange(null);
    } else if (next === OTHER_VALUE) {
      setIsCustom(true);
      onChange(normalize(customDraft));
    } else {
      setIsCustom(false);
      onChange(next);
    }
  };

  const handleCustomChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const raw = event.target.value;
    setCustomDraft(raw);
    onChange(normalize(raw));
  };

  return (
    <div className={className}>
      <select
        id={id}
        value={selectValue}
        onChange={handleSelectChange}
        disabled={disabled}
        className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:bg-gray-50 disabled:text-gray-500"
      >
        <option value={AUTO_VALUE}>Auto-detect</option>
        {CURATED_LANGUAGES.map((entry) => (
          <option key={entry.code} value={entry.code}>
            {entry.label} ({entry.code})
          </option>
        ))}
        <option value={OTHER_VALUE}>Other (custom ISO 639-1 code)</option>
      </select>
      {isCustom && (
        <input
          type="text"
          value={customDraft}
          onChange={handleCustomChange}
          disabled={disabled}
          maxLength={16}
          placeholder="e.g. sv, uk, vi"
          className="mt-2 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:bg-gray-50 disabled:text-gray-500"
          aria-label="Custom language code"
        />
      )}
    </div>
  );
};

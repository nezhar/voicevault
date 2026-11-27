import { Capability, CapabilityInfo } from '../types';

interface Props {
  catalog: CapabilityInfo[];
  selected: Capability[];
  onChange: (next: Capability[]) => void;
  /** Capabilities that may be ticked; others are shown disabled. Omit for all. */
  allowed?: Set<Capability>;
  legend?: string;
  disabled?: boolean;
}

/** Capabilities grouped by area, as checkboxes. Shared by tokens and consent. */
export function CapabilityPicker({
  catalog,
  selected,
  onChange,
  allowed,
  legend = 'Capabilities',
  disabled = false,
}: Props) {
  const areas: { area: string; items: CapabilityInfo[] }[] = [];
  catalog.forEach((item) => {
    const bucket = areas.find((entry) => entry.area === item.area);
    if (bucket) bucket.items.push(item);
    else areas.push({ area: item.area, items: [item] });
  });

  const isAllowed = (name: Capability) => !allowed || allowed.has(name);
  const toggle = (name: Capability) =>
    onChange(
      selected.includes(name) ? selected.filter((item) => item !== name) : [...selected, name],
    );
  const selectable = catalog.map((item) => item.name).filter(isAllowed);
  const allSelected = selectable.length > 0 && selectable.every((name) => selected.includes(name));

  return (
    <fieldset disabled={disabled}>
      <div className="mb-2 flex items-center justify-between">
        <legend className="text-sm font-medium text-gray-700">{legend}</legend>
        <button
          type="button"
          onClick={() => onChange(allSelected ? [] : selectable)}
          className="text-xs text-primary-600 hover:underline"
        >
          {allSelected ? 'Clear all' : 'Select all'}
        </button>
      </div>
      <div className="space-y-3">
        {areas.map(({ area, items }) => (
          <div key={area}>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
              {area}
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {items.map((item) => {
                const permitted = isAllowed(item.name);
                return (
                  <label
                    key={item.name}
                    className={`flex items-start gap-2 rounded border p-2 text-sm has-[:checked]:border-primary-600 has-[:checked]:bg-primary-50 ${
                      permitted ? 'text-gray-700' : 'cursor-not-allowed text-gray-400'
                    }`}
                    title={permitted ? undefined : 'You do not hold this capability'}
                  >
                    <input
                      type="checkbox"
                      className="mt-0.5"
                      disabled={!permitted}
                      checked={selected.includes(item.name)}
                      onChange={() => toggle(item.name)}
                    />
                    <span>
                      <span className="block font-medium">{item.label}</span>
                      <span className="block text-xs text-gray-500">{item.description}</span>
                    </span>
                  </label>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </fieldset>
  );
}

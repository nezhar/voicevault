const BYTE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];

export const formatBytes = (bytes: number): string => {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return '0 B';
  }

  // Clamp both ends: sub-byte values would otherwise index the array with -1.
  let exponent = Math.min(
    Math.max(Math.floor(Math.log(bytes) / Math.log(1024)), 0),
    BYTE_UNITS.length - 1,
  );

  // The exponent is picked before rounding, so the top sliver of each unit
  // would render as "1024.0 KB" instead of "1.0 MB". Promote it instead.
  const render = (exp: number): number => {
    const value = bytes / 1024 ** exp;
    return exp === 0 ? Math.round(value) : Number(value.toFixed(1));
  };

  if (render(exponent) >= 1024 && exponent < BYTE_UNITS.length - 1) {
    exponent += 1;
  }

  // Raw byte counts are whole numbers; everything else reads better rounded.
  return exponent === 0
    ? `${render(exponent)} ${BYTE_UNITS[exponent]}`
    : `${(bytes / 1024 ** exponent).toFixed(1)} ${BYTE_UNITS[exponent]}`;
};

export const formatHours = (seconds: number): string => {
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return '0 h';
  }

  const hours = seconds / 3600;
  // A real but tiny amount must not render as "0.0 h", which reads as nothing.
  return hours < 0.1 ? '<0.1 h' : `${hours.toFixed(1)} h`;
};

// Fixed locale so the output does not depend on the viewer's machine.
export const formatCount = (value: number): string =>
  Number.isFinite(value) ? value.toLocaleString('en-US') : '0';

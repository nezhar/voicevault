import { describe, expect, it } from 'vitest';
import { formatBytes, formatCount, formatHours } from './format';

describe('formatBytes', () => {
  it('renders zero and negatives as 0 B', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(-5)).toBe('0 B');
  });

  it('renders raw bytes without decimals', () => {
    expect(formatBytes(512)).toBe('512 B');
  });

  it('steps up through binary units', () => {
    expect(formatBytes(1024)).toBe('1.0 KB');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(1024 ** 2)).toBe('1.0 MB');
    expect(formatBytes(1024 ** 3)).toBe('1.0 GB');
    expect(formatBytes(1024 ** 4)).toBe('1.0 TB');
  });

  it('rolls over to the next unit when rounding would reach 1024', () => {
    expect(formatBytes(1048575)).toBe('1.0 MB');
    expect(formatBytes(1024 ** 3 - 1)).toBe('1.0 GB');
    expect(formatBytes(1024 ** 4 - 1)).toBe('1.0 TB');
  });

  it('keeps values below the rounding boundary in their own unit', () => {
    expect(formatBytes(1023)).toBe('1023 B');
    expect(formatBytes(1047961)).toBe('1023.4 KB');
  });

  it('does not fall off the bottom of the unit list', () => {
    expect(formatBytes(0.5)).toBe('1 B');
    expect(formatBytes(0.4)).toBe('0 B');
  });

  it('clamps at the largest known unit', () => {
    expect(formatBytes(1024 ** 6)).toBe('1024.0 PB');
  });
});

describe('formatHours', () => {
  it('renders zero as 0 h', () => {
    expect(formatHours(0)).toBe('0 h');
  });

  it('converts seconds to one decimal of hours', () => {
    expect(formatHours(3600)).toBe('1.0 h');
    expect(formatHours(5400)).toBe('1.5 h');
  });

  it('does not hide sub-hour material as zero', () => {
    expect(formatHours(60)).toBe('<0.1 h');
  });
});

describe('formatCount', () => {
  it('groups thousands', () => {
    expect(formatCount(1234567)).toBe('1,234,567');
    expect(formatCount(0)).toBe('0');
  });
});

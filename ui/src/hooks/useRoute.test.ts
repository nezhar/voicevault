import { describe, expect, it, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { parsePath, pathForRoute, useRoute } from './useRoute';

const UUID = '8f3c1d2e-4b5a-4c6d-9e8f-0a1b2c3d4e5f';

describe('parsePath', () => {
  it('maps the root to the all-entries view', () => {
    expect(parsePath('/')).toEqual({ kind: 'all' });
  });

  it('maps /mine to the personal view', () => {
    expect(parsePath('/mine')).toEqual({ kind: 'mine' });
  });

  it('maps a project permalink to the project view', () => {
    expect(parsePath(`/projects/${UUID}`)).toEqual({ kind: 'project', projectId: UUID });
  });

  it('tolerates a trailing slash', () => {
    expect(parsePath(`/projects/${UUID}/`)).toEqual({ kind: 'project', projectId: UUID });
  });

  it('falls back to the root for a non-uuid project id', () => {
    expect(parsePath('/projects/not-a-uuid')).toEqual({ kind: 'all' });
  });

  it('falls back to the root for an unknown path', () => {
    expect(parsePath('/whatever')).toEqual({ kind: 'all' });
  });
});

describe('pathForRoute', () => {
  it('round-trips every route kind', () => {
    expect(pathForRoute({ kind: 'all' })).toBe('/');
    expect(pathForRoute({ kind: 'mine' })).toBe('/mine');
    expect(pathForRoute({ kind: 'project', projectId: UUID })).toBe(`/projects/${UUID}`);
  });
});

describe('useRoute', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('starts from the current location', () => {
    window.history.replaceState({}, '', `/projects/${UUID}`);
    const { result } = renderHook(() => useRoute());
    expect(result.current.route).toEqual({ kind: 'project', projectId: UUID });
  });

  it('navigate pushes the new path and updates the route', () => {
    const { result } = renderHook(() => useRoute());
    act(() => result.current.navigate({ kind: 'project', projectId: UUID }));
    expect(window.location.pathname).toBe(`/projects/${UUID}`);
    expect(result.current.route).toEqual({ kind: 'project', projectId: UUID });
  });

  it('reacts to browser back', () => {
    const { result } = renderHook(() => useRoute());
    act(() => result.current.navigate({ kind: 'mine' }));
    act(() => {
      window.history.replaceState({}, '', '/');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    expect(result.current.route).toEqual({ kind: 'all' });
  });
});

import { useCallback, useEffect, useState } from 'react';

export type Route =
  | { kind: 'all' }
  | { kind: 'mine' }
  | { kind: 'tokens' }
  | { kind: 'admin' }
  | { kind: 'upload' }
  | { kind: 'oauth-consent' }
  | { kind: 'project'; projectId: string };

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PROJECT_PATH = /^\/projects\/([^/]+)\/?$/;

export const parsePath = (pathname: string): Route => {
  if (pathname === '/tokens') {
    return { kind: 'tokens' };
  }

  if (pathname === '/mine') {
    return { kind: 'mine' };
  }

  if (pathname === '/admin') {
    return { kind: 'admin' };
  }

  // Public page for single-use upload links; the link itself sits in the fragment.
  if (pathname === '/upload') {
    return { kind: 'upload' };
  }

  // An MCP client's OAuth sign-in waits here; its request id is the fragment.
  if (pathname === '/oauth/consent') {
    return { kind: 'oauth-consent' };
  }

  const match = PROJECT_PATH.exec(pathname);
  if (match && UUID_PATTERN.test(match[1])) {
    return { kind: 'project', projectId: match[1] };
  }

  // Anything unrecognised — including a malformed project id — goes home
  // rather than firing an API call that is guaranteed to 404.
  return { kind: 'all' };
};

export const pathForRoute = (route: Route): string => {
  switch (route.kind) {
    case 'mine':
      return '/mine';
    case 'tokens':
      return '/tokens';
    case 'project':
      return `/projects/${route.projectId}`;
    case 'admin':
      return '/admin';
    case 'upload':
      return '/upload';
    case 'oauth-consent':
      return '/oauth/consent';
    default:
      return '/';
  }
};

export const permalinkFor = (projectId: string): string =>
  `${window.location.origin}${pathForRoute({ kind: 'project', projectId })}`;

export const useRoute = () => {
  const [route, setRoute] = useState<Route>(() => parsePath(window.location.pathname));

  useEffect(() => {
    const handlePopState = () => setRoute(parsePath(window.location.pathname));
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const navigate = useCallback((next: Route) => {
    const path = pathForRoute(next);
    if (path !== window.location.pathname) {
      window.history.pushState({}, '', path);
    }
    setRoute(next);
  }, []);

  return { route, navigate };
};

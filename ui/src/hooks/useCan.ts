import { useCallback, useContext } from 'react';

import { AuthContext } from '../context/authContextValue';
import { Capability } from '../types';
import { can } from '../utils/capabilities';

/**
 * can(capability, projectId) for the signed-in user. Outside an AuthProvider
 * (isolated component tests) everything is allowed.
 */
export const useCan = () => {
  const context = useContext(AuthContext);
  const user = context?.user;
  const hasProvider = context !== undefined;
  return useCallback(
    (capability: Capability, projectId?: string | null) =>
      !hasProvider || can(user, capability, projectId),
    [hasProvider, user],
  );
};

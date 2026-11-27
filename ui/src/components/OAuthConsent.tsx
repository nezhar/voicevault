import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { KeyRound } from 'lucide-react';

import { useAuth } from '../context/AuthContext';
import { capabilityApi, oauthApi, projectApi } from '../services/api';
import { Capability, CapabilityInfo, OAuthRequestInfo, Project } from '../types';
import { heldCapabilities } from '../utils/capabilities';
import { errorFrom } from '../utils/errors';
import { CapabilityPicker } from './CapabilityPicker';

// Pre-ticked when the client names no capability: enough to read and chat.
const DEFAULT_SELECTION: Capability[] = ['entries.view', 'entries.chat', 'mcp.connect'];

const requestIdFromHash = (): string => window.location.hash.replace(/^#/, '').trim();

/**
 * Where /api/oauth/authorize sends the browser: the user sees which client
 * asks and where it will be sent back, picks what it may do, and approves or
 * denies. The result is a token the client receives, listed under API tokens.
 */
export function OAuthConsent() {
  const { user } = useAuth();
  const [request, setRequest] = useState<OAuthRequestInfo | null>(null);
  const [catalog, setCatalog] = useState<CapabilityInfo[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Capability[]>([]);
  const [limitProjects, setLimitProjects] = useState(false);
  const [projectIds, setProjectIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [gone, setGone] = useState(false);
  const [busy, setBusy] = useState(false);
  const requestId = useMemo(requestIdFromHash, []);

  const held = useMemo(() => (user?.capabilities ? heldCapabilities(user) : undefined), [user]);

  useEffect(() => {
    if (!requestId) {
      setGone(true);
      return;
    }
    let cancelled = false;
    Promise.all([oauthApi.getRequest(requestId), capabilityApi.list()])
      .then(([info, items]) => {
        if (cancelled) return;
        setRequest(info);
        setCatalog(items);
        const wanted = info.requested_capabilities.length
          ? [...info.requested_capabilities, 'mcp.connect' as Capability]
          : DEFAULT_SELECTION;
        setSelected([...new Set(wanted)].filter((cap) => !held || held.has(cap)));
      })
      .catch((err) => {
        if (cancelled) return;
        if (axios.isAxiosError(err) && err.response?.status === 404) {
          setGone(true);
        } else {
          setError(errorFrom(err, 'Could not load the sign-in request.'));
        }
      });
    projectApi
      .list()
      .then((items) => {
        if (!cancelled) setProjects(items);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [requestId, held]);

  const decide = async (approve: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const result = approve
        ? await oauthApi.approve(requestId, {
            permissions: selected,
            project_ids: limitProjects ? projectIds : null,
          })
        : await oauthApi.deny(requestId);
      window.location.assign(result.redirect_to);
    } catch (err) {
      setError(errorFrom(err, 'Could not complete the sign-in.'));
      setBusy(false);
    }
  };

  const toggleProject = (id: string) =>
    setProjectIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-10">
      <div className="mx-auto max-w-2xl space-y-6 rounded-xl border bg-white p-6 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="rounded-full bg-primary-50 p-2 text-primary-700">
            <KeyRound className="h-5 w-5" />
          </div>
          <h1 className="text-lg font-semibold text-gray-900">Connect an MCP client</h1>
        </div>

        {gone ? (
          <p className="text-sm text-gray-600">
            This sign-in request has expired or was already decided. Start the connection again from
            your MCP client.
          </p>
        ) : !request ? (
          error ? (
            <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          ) : (
            <p className="text-sm text-gray-500">Loading…</p>
          )
        ) : (
          <>
            <div className="space-y-1 text-sm text-gray-700">
              <p>
                <span className="font-medium text-gray-900">{request.client_name}</span> wants to
                use VoiceVault as <span className="font-medium">{user?.email}</span>.
              </p>
              <p className="text-xs text-gray-500">
                After you decide, your browser returns to{' '}
                <code className="break-all rounded bg-gray-100 px-1">{request.redirect_uri}</code>.
                Only continue if you started this connection yourself.
              </p>
            </div>

            {error && (
              <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
                {error}
              </div>
            )}

            <CapabilityPicker
              catalog={catalog}
              selected={selected}
              onChange={(next) => setSelected(next)}
              allowed={held}
              legend="What the client may do"
              disabled={busy}
            />
            {!selected.includes('mcp.connect') && (
              <p className="text-xs text-amber-700">
                Keep “Connect MCP clients” ticked, or the client cannot use the connection.
              </p>
            )}

            {projects.length > 0 && (
              <fieldset className="space-y-2" disabled={busy}>
                <legend className="text-sm font-medium text-gray-700">Projects</legend>
                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={limitProjects}
                    onChange={(event) => setLimitProjects(event.target.checked)}
                  />
                  Limit the client to some projects
                </label>
                {limitProjects && (
                  <div className="grid gap-1 pl-6 sm:grid-cols-2">
                    {projects.map((project) => (
                      <label
                        key={project.id}
                        className="flex items-center gap-2 text-sm text-gray-700"
                      >
                        <input
                          type="checkbox"
                          checked={projectIds.includes(project.id)}
                          onChange={() => toggleProject(project.id)}
                        />
                        {project.name}
                      </label>
                    ))}
                  </div>
                )}
              </fieldset>
            )}

            <p className="text-xs text-gray-500">
              The client receives a token listed under API tokens as “{request.client_name}{' '}
              (OAuth)”. Revoke it there to disconnect the client.
            </p>

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => decide(false)}
                disabled={busy}
                className="rounded border px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                Deny
              </button>
              <button
                type="button"
                onClick={() => decide(true)}
                disabled={
                  busy ||
                  !selected.includes('mcp.connect') ||
                  (limitProjects && projectIds.length === 0)
                }
                className="rounded bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {busy ? 'Connecting…' : 'Approve'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

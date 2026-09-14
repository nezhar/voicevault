import { useState } from 'react';

import { CopyButton } from './CopyButton';
import { SegmentedControl } from './SegmentedControl';

type Tab = 'rest' | 'mcp';

const PLACEHOLDER_TOKEN = 'vvpat_…';

const TABS: { value: Tab; label: string }[] = [
  { value: 'rest', label: 'REST API' },
  { value: 'mcp', label: 'MCP' },
];

const listEntriesExample = (origin: string, token: string): string =>
  `curl -H "Authorization: Bearer ${token}" ${origin}/api/entries/`;

const createEntryExample = (origin: string, token: string): string =>
  [
    `curl -X POST ${origin}/api/entries/url \\`,
    `  -H "Authorization: Bearer ${token}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"title": "Team meeting", "source_url": "https://example.com/meeting.mp4"}'`,
  ].join('\n');

const mcpConfigExample = (origin: string, token: string): string =>
  JSON.stringify(
    {
      mcpServers: {
        voicevault: {
          type: 'http',
          url: `${origin}/mcp`,
          headers: { Authorization: `Bearer ${token}` },
        },
      },
    },
    null,
    2,
  );

const mcpCliExample = (origin: string, token: string): string =>
  `claude mcp add --transport http voicevault ${origin}/mcp --header "Authorization: Bearer ${token}"`;

function Snippet({
  title,
  code,
  copyLabel,
  testId,
}: {
  title: string;
  code: string;
  copyLabel: string;
  testId?: string;
}) {
  return (
    <div>
      <p className="text-xs text-gray-600">{title}</p>
      <div className="mt-1 flex gap-2">
        <pre
          data-testid={testId}
          className="min-w-0 flex-1 overflow-x-auto rounded border bg-white p-2 text-xs"
        >
          {code}
        </pre>
        <CopyButton text={code} label={copyLabel} />
      </div>
    </div>
  );
}

interface Props {
  /** The freshly created secret. Omit to render the guide with a placeholder. */
  token?: string;
  /** Whether this server answers on /mcp (from GET /api/auth/config). */
  mcpEnabled: boolean;
}

/**
 * Minimal, copy-pasteable instructions for using a personal access token
 * against the REST API or the MCP server. Shown right after a token is created
 * (with the real secret) and as a collapsed reference (with a placeholder).
 */
export function IntegrationGuide({ token, mcpEnabled }: Props) {
  const [tab, setTab] = useState<Tab>('rest');
  const origin = window.location.origin;
  const secret = token ?? PLACEHOLDER_TOKEN;

  return (
    <div className="space-y-3">
      <SegmentedControl value={tab} options={TABS} onChange={setTab} label="Integration" />

      {tab === 'rest' ? (
        <div className="space-y-3 text-sm text-gray-700">
          <p>
            Base URL <code className="rounded bg-gray-100 px-1 py-0.5 text-xs">{origin}/api</code>.
            Send the token on every request as{' '}
            <code className="rounded bg-gray-100 px-1 py-0.5 text-xs">
              Authorization: Bearer {secret}
            </code>
            .
          </p>
          <Snippet
            title="List your entries"
            code={listEntriesExample(origin, secret)}
            copyLabel="Copy list example"
          />
          <Snippet
            title="Create an entry from a video or audio URL (needs Write entries)"
            code={createEntryExample(origin, secret)}
            copyLabel="Copy create example"
          />
          <p className="text-xs text-gray-500">
            Every endpoint is described in the interactive{' '}
            <a href="/api/docs" target="_blank" rel="noreferrer" className="underline">
              API docs
            </a>
            .
          </p>
        </div>
      ) : (
        <div className="space-y-3 text-sm text-gray-700">
          {!mcpEnabled && (
            <p
              role="note"
              className="rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900"
            >
              MCP is not enabled on this server. Ask an administrator to set{' '}
              <code className="rounded bg-white px-1 py-0.5">MCP_ENABLED=true</code> on the API and
              restart it.
            </p>
          )}
          <dl className="grid gap-x-4 gap-y-1 text-xs sm:grid-cols-[auto_1fr]">
            <dt className="font-medium text-gray-600">Endpoint</dt>
            <dd>
              <code className="rounded bg-gray-100 px-1 py-0.5">{origin}/mcp</code>
            </dd>
            <dt className="font-medium text-gray-600">Transport</dt>
            <dd>Streamable HTTP</dd>
            <dt className="font-medium text-gray-600">Header</dt>
            <dd>
              <code className="rounded bg-gray-100 px-1 py-0.5">
                Authorization: Bearer {secret}
              </code>
            </dd>
          </dl>
          <Snippet
            title="Client configuration (Claude Code, Claude Desktop, Cursor and other mcpServers clients)"
            code={mcpConfigExample(origin, secret)}
            copyLabel="Copy MCP config"
            testId="mcp-config"
          />
          <Snippet
            title="Or add it from the Claude Code CLI"
            code={mcpCliExample(origin, secret)}
            copyLabel="Copy MCP command"
            testId="mcp-cli"
          />
          <p className="text-xs text-gray-500">
            MCP tools use the token&apos;s permissions: reading and chatting need Read entries,
            creating or changing entries needs Write entries. Write does not include read.
          </p>
        </div>
      )}
    </div>
  );
}

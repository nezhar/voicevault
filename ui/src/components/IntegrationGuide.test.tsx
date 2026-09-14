import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { IntegrationGuide } from './IntegrationGuide';

const origin = window.location.origin;

const openMcpTab = () => fireEvent.click(screen.getByRole('button', { name: 'MCP' }));

describe('IntegrationGuide', () => {
  it('starts on the REST tab with curl examples that carry the token', () => {
    render(<IntegrationGuide token="vvpat_secret" mcpEnabled />);

    expect(screen.getByRole('button', { name: 'REST API' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    const examples = screen.getAllByText(/^curl /).map((el) => el.textContent ?? '');
    expect(examples).toHaveLength(2);
    expect(examples[0]).toContain('Authorization: Bearer vvpat_secret');
    expect(examples[0]).toContain(`${origin}/api/entries/`);
    expect(examples[1]).toContain(`${origin}/api/entries/url`);
    expect(screen.getByRole('link', { name: /API docs/ })).toHaveAttribute('href', '/api/docs');
  });

  it('uses a placeholder when no token is given, so the guide never shows a secret', () => {
    render(<IntegrationGuide mcpEnabled />);

    const examples = screen.getAllByText(/^curl /).map((el) => el.textContent ?? '');
    expect(examples[0]).toContain('Bearer vvpat_…');
    expect(examples[0]).not.toContain('vvpat_secret');
  });

  it('shows the MCP endpoint, a client config and a CLI command with the token', () => {
    render(<IntegrationGuide token="vvpat_secret" mcpEnabled />);
    openMcpTab();

    expect(screen.getByRole('button', { name: 'MCP' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(`${origin}/mcp`)).toBeInTheDocument();
    expect(screen.getByText(/Streamable HTTP/)).toBeInTheDocument();

    const config = JSON.parse(screen.getByTestId('mcp-config').textContent ?? '');
    expect(config).toEqual({
      mcpServers: {
        voicevault: {
          type: 'http',
          url: `${origin}/mcp`,
          headers: { Authorization: 'Bearer vvpat_secret' },
        },
      },
    });

    const cli = screen.getByTestId('mcp-cli').textContent ?? '';
    expect(cli).toContain(`claude mcp add --transport http voicevault ${origin}/mcp`);
    expect(cli).toContain('--header "Authorization: Bearer vvpat_secret"');
  });

  it('warns when MCP is not enabled on this server', () => {
    render(<IntegrationGuide token="vvpat_secret" mcpEnabled={false} />);
    openMcpTab();

    const notice = screen.getByRole('note');
    expect(notice).toHaveTextContent(/not enabled/i);
    expect(notice).toHaveTextContent('MCP_ENABLED=true');
    // The connection details stay visible so the user knows what to ask for.
    expect(screen.getByText(`${origin}/mcp`)).toBeInTheDocument();
  });

  it('does not warn when MCP is enabled', () => {
    render(<IntegrationGuide token="vvpat_secret" mcpEnabled />);
    openMcpTab();

    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });

  it('offers a distinct copy button for every snippet', () => {
    render(<IntegrationGuide token="vvpat_secret" mcpEnabled />);

    expect(screen.getByRole('button', { name: 'Copy list example' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy create example' })).toBeInTheDocument();
    openMcpTab();
    expect(screen.getByRole('button', { name: 'Copy MCP config' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy MCP command' })).toBeInTheDocument();
  });
});

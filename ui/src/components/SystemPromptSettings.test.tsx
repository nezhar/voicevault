import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SystemPromptSettings } from './SystemPromptSettings';

const mockPrompts = [
  {
    task: 'chat' as const,
    body: 'You are a chat assistant.',
    updated_at: '2026-04-09T00:00:00Z',
  },
  {
    task: 'summary' as const,
    body: 'You are a summary assistant.',
    updated_at: '2026-04-09T00:00:00Z',
  },
];

describe('SystemPromptSettings', () => {
  it('renders both task cards', () => {
    render(
      <SystemPromptSettings
        prompts={mockPrompts}
        isLoading={false}
        error={null}
        onUpdate={vi.fn()}
        onReset={vi.fn()}
      />
    );

    expect(screen.getByText('Chat')).toBeInTheDocument();
    expect(screen.getByText('Summary')).toBeInTheDocument();
  });

  it('shows current body in each textarea', () => {
    render(
      <SystemPromptSettings
        prompts={mockPrompts}
        isLoading={false}
        error={null}
        onUpdate={vi.fn()}
        onReset={vi.fn()}
      />
    );

    const textareas = screen.getAllByRole('textbox');
    expect(textareas[0]).toHaveValue('You are a chat assistant.');
    expect(textareas[1]).toHaveValue('You are a summary assistant.');
  });

  it('marks card dirty when body is edited', () => {
    render(
      <SystemPromptSettings
        prompts={mockPrompts}
        isLoading={false}
        error={null}
        onUpdate={vi.fn()}
        onReset={vi.fn()}
      />
    );

    const textareas = screen.getAllByRole('textbox');
    fireEvent.change(textareas[0], { target: { value: 'edited chat prompt' } });

    const saveButtons = screen.getAllByRole('button', { name: /save/i });
    expect(saveButtons[0]).not.toBeDisabled();
  });

  it('calls onUpdate with task and new body when Save is clicked', async () => {
    const onUpdate = vi.fn().mockResolvedValue(undefined);

    render(
      <SystemPromptSettings
        prompts={mockPrompts}
        isLoading={false}
        error={null}
        onUpdate={onUpdate}
        onReset={vi.fn()}
      />
    );

    const textareas = screen.getAllByRole('textbox');
    fireEvent.change(textareas[0], { target: { value: 'new chat body' } });

    const saveButtons = screen.getAllByRole('button', { name: /save/i });
    fireEvent.click(saveButtons[0]);

    await waitFor(() => {
      expect(onUpdate).toHaveBeenCalledWith('chat', 'new chat body');
    });
  });

  it('calls onReset when Reset is confirmed', async () => {
    const onReset = vi.fn().mockResolvedValue(undefined);
    window.confirm = vi.fn().mockReturnValue(true);

    render(
      <SystemPromptSettings
        prompts={mockPrompts}
        isLoading={false}
        error={null}
        onUpdate={vi.fn()}
        onReset={onReset}
      />
    );

    const resetButtons = screen.getAllByRole('button', { name: /reset/i });
    fireEvent.click(resetButtons[0]);

    await waitFor(() => {
      expect(onReset).toHaveBeenCalledWith('chat');
    });
  });

  it('does not call onReset when Reset is cancelled', () => {
    const onReset = vi.fn();
    window.confirm = vi.fn().mockReturnValue(false);

    render(
      <SystemPromptSettings
        prompts={mockPrompts}
        isLoading={false}
        error={null}
        onUpdate={vi.fn()}
        onReset={onReset}
      />
    );

    const resetButtons = screen.getAllByRole('button', { name: /reset/i });
    fireEvent.click(resetButtons[0]);

    expect(onReset).not.toHaveBeenCalled();
  });
});

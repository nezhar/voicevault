import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PromptTemplateManager } from './PromptTemplateManager';

describe('PromptTemplateManager', () => {
  it('renders templates and opens the add form', () => {
    render(
      <PromptTemplateManager
        templates={[
          {
            id: 'template-1',
            label: 'Action items',
            preview_text: 'Extract action items',
            body_markdown: '## Action Items',
            sort_order: 10,
            is_active: true,
            created_at: '2026-04-03T00:00:00Z',
            updated_at: '2026-04-03T00:00:00Z',
          },
        ]}
        isOpen
        isLoading={false}
        error={null}
        onClose={vi.fn()}
        onCreate={vi.fn()}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByText('Action items')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Add template' }));

    expect(screen.getByLabelText('Template label')).toBeInTheDocument();
    expect(screen.getByLabelText('Markdown body')).toBeInTheDocument();
  });
});

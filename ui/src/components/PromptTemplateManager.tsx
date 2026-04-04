import React, { useEffect, useMemo, useState } from 'react';
import { Pencil, Plus, Settings, Trash2, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

import { PromptTemplate, PromptTemplateCreate, PromptTemplateUpdate } from '../types';
import { PromptTemplatePreviewModal } from './PromptTemplatePreviewModal';

interface PromptTemplateManagerProps {
  templates: PromptTemplate[];
  isOpen: boolean;
  isLoading: boolean;
  error: string | null;
  onClose: () => void;
  onCreate: (template: PromptTemplateCreate) => Promise<void> | void;
  onUpdate: (id: string, template: PromptTemplateUpdate) => Promise<void> | void;
  onDelete: (id: string) => Promise<void> | void;
}

interface TemplateFormState {
  label: string;
  preview_text: string;
  body_markdown: string;
  sort_order: number;
  is_active: boolean;
}

const createEmptyForm = (templates: PromptTemplate[]): TemplateFormState => ({
  label: '',
  preview_text: '',
  body_markdown: '',
  sort_order: templates.length > 0 ? Math.max(...templates.map(template => template.sort_order)) + 10 : 10,
  is_active: true,
});

const mapTemplateToForm = (template: PromptTemplate): TemplateFormState => ({
  label: template.label,
  preview_text: template.preview_text ?? '',
  body_markdown: template.body_markdown,
  sort_order: template.sort_order,
  is_active: template.is_active,
});

export const PromptTemplateManager: React.FC<PromptTemplateManagerProps> = ({
  templates,
  isOpen,
  isLoading,
  error,
  onClose,
  onCreate,
  onUpdate,
  onDelete,
}) => {
  const [editingTemplateId, setEditingTemplateId] = useState<string | null>(null);
  const [formState, setFormState] = useState<TemplateFormState>(() => createEmptyForm(templates));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [previewTemplate, setPreviewTemplate] = useState<PromptTemplate | null>(null);

  const sortedTemplates = useMemo(
    () => [...templates].sort((left, right) => left.sort_order - right.sort_order || left.label.localeCompare(right.label)),
    [templates]
  );

  useEffect(() => {
    if (!isOpen) {
      setEditingTemplateId(null);
      setFormState(createEmptyForm(templates));
      setSubmitError(null);
      return;
    }

    if (editingTemplateId === null) {
      setFormState(createEmptyForm(templates));
      setSubmitError(null);
    }
  }, [isOpen, templates, editingTemplateId]);

  if (!isOpen) {
    return null;
  }

  const resetForm = () => {
    setEditingTemplateId(null);
    setFormState(createEmptyForm(templates));
    setSubmitError(null);
  };

  const openCreateForm = () => {
    setEditingTemplateId(null);
    setFormState(createEmptyForm(templates));
    setSubmitError(null);
  };

  const openEditForm = (template: PromptTemplate) => {
    setEditingTemplateId(template.id);
    setFormState(mapTemplateToForm(template));
    setSubmitError(null);
  };

  const handleChange = <K extends keyof TemplateFormState>(field: K, value: TemplateFormState[K]) => {
    setFormState(prev => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (!formState.label.trim() || !formState.body_markdown.trim()) {
      setSubmitError('Template label and markdown body are required.');
      return;
    }

    const payload = {
      label: formState.label.trim(),
      preview_text: formState.preview_text.trim(),
      body_markdown: formState.body_markdown,
      sort_order: formState.sort_order,
      is_active: formState.is_active,
    };

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      if (editingTemplateId) {
        await onUpdate(editingTemplateId, payload);
      } else {
        await onCreate(payload);
      }
      resetForm();
    } catch (submitFailure) {
      console.error('Failed to save prompt template:', submitFailure);
      setSubmitError('Failed to save template. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (templateId: string, label: string) => {
    if (!window.confirm(`Delete the template "${label}"?`)) {
      return;
    }

    try {
      await onDelete(templateId);
      if (editingTemplateId === templateId) {
        resetForm();
      }
    } catch (deleteFailure) {
      console.error('Failed to delete prompt template:', deleteFailure);
      setSubmitError('Failed to delete template. Please try again.');
    }
  };

  const handleToggleActive = async (template: PromptTemplate) => {
    try {
      await onUpdate(template.id, { is_active: !template.is_active });
      if (editingTemplateId === template.id) {
        setFormState(prev => ({
          ...prev,
          is_active: !template.is_active,
        }));
      }
    } catch (updateFailure) {
      console.error('Failed to update prompt template:', updateFailure);
      setSubmitError('Failed to update template. Please try again.');
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4">
        <div className="flex h-[85vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl md:flex-row">
          <div className="flex w-full flex-col border-b border-gray-200 md:w-[360px] md:border-b-0 md:border-r">
            <div className="flex items-center justify-between px-5 py-4">
              <div className="flex items-center gap-3">
                <div className="rounded-full bg-gray-100 p-2 text-gray-700">
                  <Settings className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Prompt Templates</h2>
                  <p className="text-sm text-gray-500">Global templates for chat starters</p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="rounded-md p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                aria-label="Close prompt templates"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="border-y border-gray-100 px-5 py-3">
              <button
                onClick={openCreateForm}
                className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700"
              >
                <Plus className="h-4 w-4" />
                Add template
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4">
              {isLoading && <p className="text-sm text-gray-500">Loading templates...</p>}
              {!isLoading && error && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {error}
                </div>
              )}
              {!isLoading && !error && sortedTemplates.length === 0 && (
                <p className="text-sm text-gray-500">No templates yet.</p>
              )}
              <div className="space-y-3">
                {sortedTemplates.map(template => (
                  <div
                    key={template.id}
                    className={`rounded-xl border p-3 transition-colors ${
                      editingTemplateId === template.id ? 'border-primary-300 bg-primary-50/50' : 'border-gray-200'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-medium text-gray-900">{template.label}</p>
                        <p className="mt-1 text-sm text-gray-500">
                          {template.preview_text || 'No preview text'}
                        </p>
                      </div>
                      <span
                        className={`rounded-full px-2 py-1 text-[11px] font-medium ${
                          template.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                        }`}
                      >
                        {template.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        onClick={() => openEditForm(template)}
                        className="inline-flex items-center gap-1 rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50"
                      >
                        <Pencil className="h-3 w-3" />
                        Edit
                      </button>
                      <button
                        onClick={() => setPreviewTemplate(template)}
                        className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50"
                      >
                        Preview
                      </button>
                      <button
                        onClick={() => handleToggleActive(template)}
                        className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50"
                      >
                        {template.is_active ? 'Disable' : 'Enable'}
                      </button>
                      <button
                        onClick={() => handleDelete(template.id, template.label)}
                        className="inline-flex items-center gap-1 rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-50"
                      >
                        <Trash2 className="h-3 w-3" />
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-5 md:px-6">
            <div className="mb-5">
              <h3 className="text-lg font-semibold text-gray-900">
                {editingTemplateId ? 'Edit template' : 'Create template'}
              </h3>
              <p className="text-sm text-gray-500">
                Use markdown for reusable chat prompts. The live preview shows how the content will render.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="template-label" className="mb-1 block text-sm font-medium text-gray-700">
                  Template label
                </label>
                <input
                  id="template-label"
                  value={formState.label}
                  onChange={(event) => handleChange('label', event.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
                />
              </div>

              <div>
                <label htmlFor="template-preview" className="mb-1 block text-sm font-medium text-gray-700">
                  Preview text
                </label>
                <input
                  id="template-preview"
                  value={formState.preview_text}
                  onChange={(event) => handleChange('preview_text', event.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
                  placeholder="Short summary shown in chat"
                />
              </div>

              <div className="grid gap-4 md:grid-cols-[160px,1fr]">
                <div>
                  <label htmlFor="template-sort-order" className="mb-1 block text-sm font-medium text-gray-700">
                    Sort order
                  </label>
                  <input
                    id="template-sort-order"
                    type="number"
                    value={formState.sort_order}
                    onChange={(event) => handleChange('sort_order', Number(event.target.value))}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
                  />
                </div>
                <label className="mt-7 inline-flex items-center gap-2 text-sm font-medium text-gray-700">
                  <input
                    type="checkbox"
                    checked={formState.is_active}
                    onChange={(event) => handleChange('is_active', event.target.checked)}
                    className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                  />
                  Active in chat selector
                </label>
              </div>

              <div>
                <label htmlFor="template-body" className="mb-1 block text-sm font-medium text-gray-700">
                  Markdown body
                </label>
                <textarea
                  id="template-body"
                  value={formState.body_markdown}
                  onChange={(event) => handleChange('body_markdown', event.target.value)}
                  rows={12}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 font-mono text-sm focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
                />
              </div>

              {(submitError || error) && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {submitError || error}
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isSubmitting ? 'Saving...' : editingTemplateId ? 'Save changes' : 'Create template'}
                </button>
                <button
                  type="button"
                  onClick={resetForm}
                  className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
                >
                  Clear
                </button>
              </div>
            </form>

            <div className="mt-8">
              <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">Live preview</h4>
              <div className="prose prose-sm mt-3 max-w-none rounded-xl border border-gray-200 bg-gray-50 px-4 py-4">
                {formState.body_markdown.trim() ? (
                  <ReactMarkdown>{formState.body_markdown}</ReactMarkdown>
                ) : (
                  <p>Template markdown preview will appear here.</p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <PromptTemplatePreviewModal
        bodyMarkdown={previewTemplate?.body_markdown ?? ''}
        isOpen={previewTemplate !== null}
        title={previewTemplate?.label ?? 'Template preview'}
        onClose={() => setPreviewTemplate(null)}
      />
    </>
  );
};

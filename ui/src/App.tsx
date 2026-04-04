import { useState, useEffect, useCallback } from 'react';
import { Mic, Brain, Zap, LogOut, Plus, Settings } from 'lucide-react';

import { EntryForm } from './components/EntryForm';
import { EntryList } from './components/EntryList';
import { ChatInterface } from './components/ChatInterface';
import { Login } from './components/Login';
import { PromptTemplateManager } from './components/PromptTemplateManager';
import { SearchBar } from './components/SearchBar';
import { entryApi, auth } from './services/api';
import { Entry, PromptTemplate, PromptTemplateCreate, PromptTemplateUpdate } from './types';
import 'highlight.js/styles/github.css';

type EntryFilter = 'active' | 'archived';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [promptTemplates, setPromptTemplates] = useState<PromptTemplate[]>([]);
  const [promptTemplatesLoading, setPromptTemplatesLoading] = useState(false);
  const [promptTemplatesError, setPromptTemplatesError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedEntry, setSelectedEntry] = useState<Entry | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [isAddEntryOpen, setIsAddEntryOpen] = useState(false);
  const [isTemplateManagerOpen, setIsTemplateManagerOpen] = useState(false);
  const [entryFilter, setEntryFilter] = useState<EntryFilter>('active');
  const isArchivedView = entryFilter === 'archived';

  const sortPromptTemplates = useCallback((templatesToSort: PromptTemplate[]) => (
    [...templatesToSort].sort((left, right) => left.sort_order - right.sort_order || left.label.localeCompare(right.label))
  ), []);

  const fetchEntries = useCallback(async (currentPage: number = 1, append: boolean = false) => {
    try {
      const response = await entryApi.getEntries(
        currentPage,
        12,
        searchQuery || undefined,
        isArchivedView
      );

      if (append) {
        setEntries(prev => [...prev, ...response.entries]);
      } else {
        setEntries(response.entries);
      }

      setTotal(response.total);
    } catch (error) {
      console.error('Failed to fetch entries:', error);
    } finally {
      setLoading(false);
      setIsLoadingMore(false);
    }
  }, [searchQuery, isArchivedView]);

  const fetchPromptTemplates = useCallback(async () => {
    setPromptTemplatesLoading(true);
    setPromptTemplatesError(null);

    try {
      const templates = await entryApi.getPromptTemplates(false);
      setPromptTemplates(sortPromptTemplates(templates));
    } catch (error) {
      console.error('Failed to fetch prompt templates:', error);
      setPromptTemplatesError('Failed to load prompt templates.');
    } finally {
      setPromptTemplatesLoading(false);
    }
  }, [sortPromptTemplates]);

  useEffect(() => {
    if (auth.isAuthenticated()) {
      setIsAuthenticated(true);
    } else {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      setLoading(true);
      setPage(1);
      setAutoRefreshEnabled(!isArchivedView && !searchQuery);
      fetchEntries(1, false);
    }
  }, [searchQuery, isAuthenticated, fetchEntries, isArchivedView]);

  useEffect(() => {
    if (isAuthenticated) {
      fetchPromptTemplates();
    }
  }, [isAuthenticated, fetchPromptTemplates]);

  useEffect(() => {
    if (isAuthenticated && autoRefreshEnabled && page === 1 && !searchQuery && !isArchivedView) {
      const interval = setInterval(() => {
        fetchEntries(1, false);
      }, 10000);
      return () => clearInterval(interval);
    }
  }, [isAuthenticated, autoRefreshEnabled, page, searchQuery, fetchEntries, isArchivedView]);

  const handleEntryCreated = (newEntry: Entry) => {
    if (!isArchivedView) {
      setEntries(prev => [newEntry, ...prev]);
      setTotal(prev => prev + 1);
    }
    setIsAddEntryOpen(false);
  };

  const handleOpenChat = (entry: Entry) => {
    setSelectedEntry(entry);
  };

  const handleCloseChat = () => {
    setSelectedEntry(null);
  };

  const handleLogin = () => {
    setIsAuthenticated(true);
    setLoading(true);
  };

  const handleLogout = () => {
    auth.removeToken();
    setIsAuthenticated(false);
    setEntries([]);
    setPromptTemplates([]);
    setPromptTemplatesError(null);
    setSelectedEntry(null);
    setPage(1);
    setSearchQuery('');
    setIsAddEntryOpen(false);
    setIsTemplateManagerOpen(false);
    setEntryFilter('active');
  };

  const handleDeleteEntry = async (entry: Entry) => {
    try {
      await entryApi.deleteEntry(entry.id);
      setEntries(prev => prev.filter(e => e.id !== entry.id));
      setTotal(prev => prev - 1);

      if (selectedEntry?.id === entry.id) {
        setSelectedEntry(null);
      }
    } catch (error) {
      console.error('Failed to delete entry:', error);
      throw error;
    }
  };

  const handleLoadMore = () => {
    setIsLoadingMore(true);
    const nextPage = page + 1;
    setPage(nextPage);
    setAutoRefreshEnabled(false);
    fetchEntries(nextPage, true);
  };

  const handleRefresh = () => {
    setPage(1);
    setAutoRefreshEnabled(!isArchivedView && !searchQuery);
    fetchEntries(1, false);
  };

  const handleSearchChange = (query: string) => {
    setSearchQuery(query);
  };

  const handleFilterChange = (filter: EntryFilter) => {
    setEntryFilter(filter);
  };

  const handleToggleArchive = async (entry: Entry, archived: boolean) => {
    const updatedEntry = await entryApi.setArchived(entry.id, archived);

    if (updatedEntry.archived === isArchivedView) {
      setEntries(prev => prev.map(currentEntry => (
        currentEntry.id === updatedEntry.id ? updatedEntry : currentEntry
      )));
      return;
    }

    setEntries(prev => prev.filter(currentEntry => currentEntry.id !== updatedEntry.id));
    setTotal(prev => Math.max(prev - 1, 0));
  };

  const handleCreatePromptTemplate = async (template: PromptTemplateCreate) => {
    const createdTemplate = await entryApi.createPromptTemplate(template);
    setPromptTemplates(prev => sortPromptTemplates([...prev, createdTemplate]));
  };

  const handleUpdatePromptTemplate = async (id: string, template: PromptTemplateUpdate) => {
    const updatedTemplate = await entryApi.updatePromptTemplate(id, template);
    setPromptTemplates(prev => sortPromptTemplates(
      prev.map(currentTemplate => currentTemplate.id === id ? updatedTemplate : currentTemplate)
    ));
  };

  const handleDeletePromptTemplate = async (id: string) => {
    await entryApi.deletePromptTemplate(id);
    setPromptTemplates(prev => prev.filter(template => template.id !== id));
  };

  const hasMore = entries.length < total;

  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center space-x-3">
              <div className="flex items-center justify-center w-10 h-10 bg-primary-600 rounded-lg">
                <Mic className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">VoiceVault</h1>
                <p className="text-sm text-gray-500">Enterprise Voice Intelligence</p>
              </div>
            </div>

            <div className="hidden md:flex items-center space-x-6 text-sm text-gray-600">
              <div className="flex items-center space-x-2">
                <Brain className="h-4 w-4 text-primary-600" />
                <span>AI-Powered Analysis</span>
              </div>
              <div className="flex items-center space-x-2">
                <Zap className="h-4 w-4 text-primary-600" />
                <span>Real-time Processing</span>
              </div>
              <button
                onClick={handleLogout}
                className="flex items-center space-x-2 text-gray-600 transition-colors hover:text-gray-900"
                title="Logout"
              >
                <LogOut className="h-4 w-4" />
                <span>Logout</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="space-y-8">
          <div className="flex flex-col gap-3 md:flex-row md:items-center">
            <div className="flex-1">
              <SearchBar
                value={searchQuery}
                onChange={handleSearchChange}
              />
            </div>
            <div className="inline-flex rounded-lg border border-gray-200 bg-white p-1">
              <button
                onClick={() => handleFilterChange('active')}
                className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  !isArchivedView
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                Active
              </button>
              <button
                onClick={() => handleFilterChange('archived')}
                className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  isArchivedView
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                Archived
              </button>
            </div>
            <button
              onClick={() => setIsAddEntryOpen(true)}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 py-2 font-medium text-white transition-colors hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
              aria-label="Add new entry"
            >
              <Plus className="h-4 w-4" />
              Add
            </button>
          </div>

          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto"></div>
              <p className="mt-2 text-gray-500">Loading entries...</p>
            </div>
          ) : (
            <EntryList
              entries={entries}
              total={total}
              hasMore={hasMore}
              isLoadingMore={isLoadingMore}
              isArchivedView={isArchivedView}
              onRefresh={handleRefresh}
              onOpenChat={handleOpenChat}
              onDelete={handleDeleteEntry}
              onToggleArchive={handleToggleArchive}
              onLoadMore={handleLoadMore}
              isSearching={!!searchQuery}
            />
          )}
        </div>
      </main>

      {isAddEntryOpen && (
        <EntryForm
          onEntryCreated={handleEntryCreated}
          onClose={() => setIsAddEntryOpen(false)}
        />
      )}

      {selectedEntry && (
        <ChatInterface
          entry={selectedEntry}
          onClose={handleCloseChat}
        />
      )}

      <button
        onClick={() => setIsTemplateManagerOpen(true)}
        className="fixed z-30 inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-700 shadow-lg transition-colors hover:bg-gray-50"
        style={{
          left: 'max(1rem, env(safe-area-inset-left))',
          bottom: 'max(1rem, env(safe-area-inset-bottom))',
        }}
        aria-label="Open prompt template settings"
      >
        <Settings className="h-4 w-4" />
        <span>Templates</span>
      </button>

      <PromptTemplateManager
        templates={promptTemplates}
        isOpen={isTemplateManagerOpen}
        isLoading={promptTemplatesLoading}
        error={promptTemplatesError}
        onClose={() => setIsTemplateManagerOpen(false)}
        onCreate={handleCreatePromptTemplate}
        onUpdate={handleUpdatePromptTemplate}
        onDelete={handleDeletePromptTemplate}
      />
    </div>
  );
}

export default App;

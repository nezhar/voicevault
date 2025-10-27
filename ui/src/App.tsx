import React, { useState, useEffect, useCallback } from 'react';
import { Mic, Brain, Zap, LogOut } from 'lucide-react';
import { EntryForm } from './components/EntryForm';
import { EntryList } from './components/EntryList';
import { ChatInterface } from './components/ChatInterface';
import { Login } from './components/Login';
import { SearchBar } from './components/SearchBar';
import { entryApi, auth } from './services/api';
import { Entry } from './types';
import 'highlight.js/styles/github.css';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedEntry, setSelectedEntry] = useState<Entry | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);

  const fetchEntries = useCallback(async (currentPage: number = 1, append: boolean = false) => {
    try {
      const response = await entryApi.getEntries(currentPage, 12, searchQuery || undefined);

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
  }, [searchQuery]);

  useEffect(() => {
    // Check if user is already authenticated
    if (auth.isAuthenticated()) {
      setIsAuthenticated(true);
    } else {
      setLoading(false);
    }
  }, []);

  // Fetch entries when search query changes
  useEffect(() => {
    if (isAuthenticated) {
      setLoading(true);
      setPage(1);
      setAutoRefreshEnabled(false); // Disable auto-refresh when searching
      fetchEntries(1, false);

      // Re-enable auto-refresh after 2 seconds if search is empty
      if (!searchQuery) {
        const timer = setTimeout(() => {
          setAutoRefreshEnabled(true);
        }, 2000);
        return () => clearTimeout(timer);
      }
    }
  }, [searchQuery, isAuthenticated, fetchEntries]);

  // Auto-refresh entries when enabled
  useEffect(() => {
    if (isAuthenticated && autoRefreshEnabled && page === 1 && !searchQuery) {
      const interval = setInterval(() => {
        fetchEntries(1, false);
      }, 10000);
      return () => clearInterval(interval);
    }
  }, [isAuthenticated, autoRefreshEnabled, page, searchQuery, fetchEntries]);

  const handleEntryCreated = (newEntry: Entry) => {
    setEntries(prev => [newEntry, ...prev]);
    setTotal(prev => prev + 1);
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
    setSelectedEntry(null);
    setPage(1);
    setSearchQuery('');
  };

  const handleDeleteEntry = async (entry: Entry) => {
    try {
      await entryApi.deleteEntry(entry.id);

      // Remove the entry from the local state
      setEntries(prev => prev.filter(e => e.id !== entry.id));
      setTotal(prev => prev - 1);

      // Close chat if this entry was being viewed
      if (selectedEntry?.id === entry.id) {
        setSelectedEntry(null);
      }
    } catch (error) {
      console.error('Failed to delete entry:', error);
      throw error; // Re-throw to let the component handle the error display
    }
  };

  const handleLoadMore = () => {
    setIsLoadingMore(true);
    const nextPage = page + 1;
    setPage(nextPage);
    setAutoRefreshEnabled(false); // Disable auto-refresh when paginating
    fetchEntries(nextPage, true);
  };

  const handleRefresh = () => {
    setPage(1);
    setAutoRefreshEnabled(true);
    fetchEntries(1, false);
  };

  const handleSearchChange = (query: string) => {
    setSearchQuery(query);
  };

  const hasMore = entries.length < total;

  // Show login screen if not authenticated
  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
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
                className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
                title="Logout"
              >
                <LogOut className="h-4 w-4" />
                <span>Logout</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="space-y-8">
          {/* Entry form */}
          <EntryForm onEntryCreated={handleEntryCreated} />

          {/* Search bar */}
          <SearchBar
            value={searchQuery}
            onChange={handleSearchChange}
          />

          {/* Entry list */}
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
              onRefresh={handleRefresh}
              onOpenChat={handleOpenChat}
              onDelete={handleDeleteEntry}
              onLoadMore={handleLoadMore}
              isSearching={!!searchQuery}
            />
          )}
        </div>
      </main>

      {/* Chat interface modal */}
      {selectedEntry && (
        <ChatInterface
          entry={selectedEntry}
          onClose={handleCloseChat}
        />
      )}
    </div>
  );
}

export default App;
import React, { useState, useEffect } from 'react';
import { Mic, Brain, Zap } from 'lucide-react';
import { EntryForm } from './components/EntryForm';
import { EntryList } from './components/EntryList';
import { ChatInterface } from './components/ChatInterface';
import { entryApi } from './services/api';
import { Entry } from './types';
import 'highlight.js/styles/github.css';

function App() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedEntry, setSelectedEntry] = useState<Entry | null>(null);

  const fetchEntries = async () => {
    try {
      const response = await entryApi.getEntries(1, 20);
      setEntries(response.entries);
    } catch (error) {
      console.error('Failed to fetch entries:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEntries();
    
    // Auto-refresh entries every 10 seconds to update status
    const interval = setInterval(fetchEntries, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleEntryCreated = (newEntry: Entry) => {
    setEntries(prev => [newEntry, ...prev]);
  };

  const handleOpenChat = (entry: Entry) => {
    setSelectedEntry(entry);
  };

  const handleCloseChat = () => {
    setSelectedEntry(null);
  };

  const handleDeleteEntry = async (entry: Entry) => {
    try {
      await entryApi.deleteEntry(entry.id);
      
      // Remove the entry from the local state
      setEntries(prev => prev.filter(e => e.id !== entry.id));
      
      // Close chat if this entry was being viewed
      if (selectedEntry?.id === entry.id) {
        setSelectedEntry(null);
      }
    } catch (error) {
      console.error('Failed to delete entry:', error);
      throw error; // Re-throw to let the component handle the error display
    }
  };

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
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="space-y-8">
          {/* Entry form */}
          <EntryForm onEntryCreated={handleEntryCreated} />
          
          {/* Entry list */}
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto"></div>
              <p className="mt-2 text-gray-500">Loading entries...</p>
            </div>
          ) : (
            <EntryList
              entries={entries}
              onRefresh={fetchEntries}
              onOpenChat={handleOpenChat}
              onDelete={handleDeleteEntry}
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
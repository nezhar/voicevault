import React, { useState, useRef, useEffect } from 'react';
import { Send, X, FileText, AlertCircle, Eye, EyeOff } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { Entry, ChatMessage } from '../types';
import { entryApi } from '../services/api';

interface ChatInterfaceProps {
  entry: Entry;
  onClose: () => void;
}

interface Message {
  id: string;
  content: string;
  sender: 'user' | 'assistant';
  timestamp: Date;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({ entry, onClose }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTranscript, setShowTranscript] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Check if entry is ready for chat
  const isEntryReady = entry.status === 'READY' && entry.transcript;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Initialize chat with welcome message
  useEffect(() => {
    if (isEntryReady) {
      setMessages([
        {
          id: '1',
          content: `Hi! I'm ready to help you analyze the content from "${entry.title}". You can ask me questions about the transcript, request summaries, or explore specific topics mentioned in the audio.`,
          sender: 'assistant',
          timestamp: new Date(),
        },
      ]);
    }
  }, [entry.title, isEntryReady]);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || isLoading || !isEntryReady) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      content: inputValue.trim(),
      sender: 'user',
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    setError(null);

    try {
      // Prepare conversation history for API
      const conversationHistory: ChatMessage[] = messages.map(msg => ({
        role: msg.sender,
        content: msg.content,
        timestamp: msg.timestamp.toISOString(),
      }));

      // Call the chat API
      const response = await entryApi.chatWithEntry(entry.id, {
        message: userMessage.content,
        conversation_history: conversationHistory,
      });

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: response.message,
        sender: 'assistant',
        timestamp: new Date(response.timestamp),
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Chat error:', error);
      setError('Failed to get response. Please try again.');
      
      // Add error message to chat
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: 'I apologize, but I encountered an error while processing your message. Please try again.',
        sender: 'assistant',
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  };

  const handleQuestionClick = (question: string) => {
    setInputValue(question);
  };

  const suggestedQuestions = [
    "What are the key points?",
    "Summarize this content",
    "What questions were discussed?",
    "What action items were mentioned?",
    "What are the main themes?",
    "Who were the speakers?"
  ];

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <div className="flex items-center space-x-3">
            <FileText className="h-5 w-5 text-primary-600" />
            <div>
              <h3 className="font-semibold text-gray-900">{entry.title}</h3>
              <div className="flex items-center space-x-2">
                <p className="text-sm text-gray-500">
                  Chat about this content • {entry.transcript?.length || 0} characters
                </p>
                {entry.transcript && (
                  <button
                    onClick={() => setShowTranscript(!showTranscript)}
                    className="inline-flex items-center px-2 py-1 text-xs text-primary-600 hover:text-primary-700 hover:bg-primary-50 rounded transition-colors"
                    title={showTranscript ? "Hide transcript" : "View transcript"}
                  >
                    {showTranscript ? (
                      <>
                        <EyeOff className="h-3 w-3 mr-1" />
                        Hide
                      </>
                    ) : (
                      <>
                        <Eye className="h-3 w-3 mr-1" />
                        View
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Transcript Display */}
        {showTranscript && entry.transcript && (
          <div className="border-b border-gray-200 bg-gray-50">
            <div className="p-4 max-h-48 overflow-y-auto">
              <h4 className="text-sm font-medium text-gray-900 mb-2">Transcript</h4>
              <div className="text-sm text-gray-700 whitespace-pre-wrap">
                {entry.transcript}
              </div>
            </div>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {!isEntryReady ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <AlertCircle className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">
                  {entry.status === 'NEW' || entry.status === 'IN_PROGRESS' ? 
                    'Processing in Progress' : 
                    'Transcript Not Available'
                  }
                </h3>
                <p className="text-gray-500">
                  {entry.status === 'NEW' || entry.status === 'IN_PROGRESS' ? 
                    'Please wait for the transcript to be generated before starting a chat.' :
                    'This entry doesn\'t have a transcript available for chatting.'
                  }
                </p>
                <p className="text-sm text-gray-400 mt-2">
                  Current status: {entry.status}
                </p>
              </div>
            </div>
          ) : (
            <>
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[70%] rounded-lg px-4 py-2 ${
                      message.sender === 'user'
                        ? 'bg-primary-600 text-white'
                        : 'bg-gray-100 text-gray-900'
                    }`}
                  >
                    <div className="text-sm">
                      {message.sender === 'user' ? (
                        <p>{message.content}</p>
                      ) : (
                        <ReactMarkdown
                          components={{
                            // Custom styling for markdown elements
                            p: ({ children }) => (
                              <p className="mb-2 last:mb-0">
                                {children}
                              </p>
                            ),
                            ul: ({ children }) => (
                              <ul className="list-disc list-inside mb-2 space-y-1">
                                {children}
                              </ul>
                            ),
                            ol: ({ children }) => (
                              <ol className="list-decimal list-inside mb-2 space-y-1">
                                {children}
                              </ol>
                            ),
                            li: ({ children }) => (
                              <li className="mb-1">
                                {children}
                              </li>
                            ),
                            strong: ({ children }) => (
                              <strong className="font-semibold">
                                {children}
                              </strong>
                            ),
                            em: ({ children }) => (
                              <em className="italic">
                                {children}
                              </em>
                            ),
                            code: ({ children, inline }) => {
                              if (inline) {
                                return (
                                  <code className="bg-gray-200 text-gray-800 px-1 py-0.5 rounded text-xs font-mono">
                                    {children}
                                  </code>
                                );
                              }
                              return (
                                <pre className="bg-gray-800 text-green-400 p-2 rounded text-xs overflow-x-auto my-2">
                                  <code>
                                    {children}
                                  </code>
                                </pre>
                              );
                            },
                            blockquote: ({ children }) => (
                              <blockquote className="border-l-4 border-gray-300 pl-4 italic my-2">
                                {children}
                              </blockquote>
                            ),
                            h1: ({ children }) => (
                              <h1 className="text-lg font-bold mb-2">
                                {children}
                              </h1>
                            ),
                            h2: ({ children }) => (
                              <h2 className="text-base font-bold mb-2">
                                {children}
                              </h2>
                            ),
                            h3: ({ children }) => (
                              <h3 className="text-sm font-bold mb-2">
                                {children}
                              </h3>
                            ),
                          }}
                        >
                          {message.content}
                        </ReactMarkdown>
                      )}
                    </div>
                    <p
                      className={`text-xs mt-1 ${
                        message.sender === 'user' ? 'text-primary-100' : 'text-gray-500'
                      }`}
                    >
                      {formatTime(message.timestamp)}
                    </p>
                  </div>
                </div>
              ))}
              
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-gray-100 rounded-lg px-4 py-2">
                    <div className="flex space-x-1">
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100" />
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200" />
                    </div>
                  </div>
                </div>
              )}
              
              {error && (
                <div className="flex justify-start">
                  <div className="bg-red-100 border border-red-200 rounded-lg px-4 py-2">
                    <p className="text-sm text-red-700">{error}</p>
                  </div>
                </div>
              )}
            </>
          )}
          
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-gray-200 p-4">
          <form onSubmit={handleSendMessage} className="flex space-x-2">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={isEntryReady ? "Ask about the content..." : "Waiting for transcript..."}
              disabled={isLoading || !isEntryReady}
              className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!inputValue.trim() || isLoading || !isEntryReady}
              className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
          
          {isEntryReady && messages.length <= 1 && (
            <div className="mt-3">
              <p className="text-xs text-gray-500 mb-2">💡 Try asking:</p>
              <div className="flex flex-wrap gap-2">
                {suggestedQuestions.map((question, index) => (
                  <button
                    key={index}
                    onClick={() => handleQuestionClick(question)}
                    disabled={isLoading}
                    className="px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-full border border-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          )}
          
          {!isEntryReady && (
            <div className="mt-2 text-xs text-gray-500">
              ⏳ Chat will be available once the transcript is ready
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
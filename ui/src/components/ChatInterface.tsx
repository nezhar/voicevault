import React, { useState, useRef, useEffect } from 'react';
import { Send, X, FileText, AlertCircle, Eye, EyeOff, Copy, Check } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { Entry, ChatMessage, PromptTemplate } from '../types';
import { entryApi } from '../services/api';
import { PromptTemplatePreviewModal } from './PromptTemplatePreviewModal';

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
  const [promptTemplates, setPromptTemplates] = useState<PromptTemplate[]>([]);
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false);
  const [promptTemplatesError, setPromptTemplatesError] = useState<string | null>(null);
  const [previewTemplate, setPreviewTemplate] = useState<PromptTemplate | null>(null);
  const [showTranscript, setShowTranscript] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
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

  useEffect(() => {
    let isCurrent = true;

    if (!isEntryReady) {
      setPromptTemplates([]);
      setPromptTemplatesError(null);
      setIsLoadingTemplates(false);
      return () => {
        isCurrent = false;
      };
    }

    setIsLoadingTemplates(true);
    setPromptTemplatesError(null);

    entryApi.getPromptTemplates(true)
      .then((templates) => {
        if (!isCurrent) {
          return;
        }
        setPromptTemplates(templates);
      })
      .catch((templateError) => {
        console.error('Failed to load prompt templates:', templateError);
        if (isCurrent) {
          setPromptTemplates([]);
          setPromptTemplatesError('Prompt templates are unavailable right now.');
        }
      })
      .finally(() => {
        if (isCurrent) {
          setIsLoadingTemplates(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [entry.id, isEntryReady]);

  const submitMessage = async (content: string) => {
    const trimmedMessage = content.trim();
    if (!trimmedMessage || isLoading || !isEntryReady) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      content: trimmedMessage,
      sender: 'user',
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    setError(null);

    try {
      const conversationHistory: ChatMessage[] = messages.map(msg => ({
        role: msg.sender,
        content: msg.content,
        timestamp: msg.timestamp.toISOString(),
      }));

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
    } catch (chatError) {
      console.error('Chat error:', chatError);
      setError('Failed to get response. Please try again.');

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

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    await submitMessage(inputValue);
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

  const handleTemplateUse = async (template: PromptTemplate, sendImmediately: boolean) => {
    if (sendImmediately) {
      await submitMessage(template.body_markdown);
      return;
    }

    setInputValue(template.body_markdown);
  };

  const copyToClipboard = async (content: string, messageId: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageId(messageId);
      // Reset the copied state after 2 seconds
      setTimeout(() => setCopiedMessageId(null), 2000);
    } catch (error) {
      console.error('Failed to copy to clipboard:', error);
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = content;
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        setCopiedMessageId(messageId);
        setTimeout(() => setCopiedMessageId(null), 2000);
      } catch (fallbackError) {
        console.error('Fallback copy failed:', fallbackError);
      }
      document.body.removeChild(textArea);
    }
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
                        <p className="whitespace-pre-wrap">{message.content}</p>
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
                            code: ({ children, className }) => {
                              const content = String(children);
                              const isBlockCode = Boolean(className) || content.includes('\n');

                              if (!isBlockCode) {
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
                    <div className={`flex items-center justify-between mt-1 ${
                      message.sender === 'user' ? 'text-primary-100' : 'text-gray-500'
                    }`}>
                      <p className="text-xs">
                        {formatTime(message.timestamp)}
                      </p>
                      {message.sender === 'assistant' && (
                        <button
                          onClick={() => copyToClipboard(message.content, message.id)}
                          className={`ml-2 p-1 rounded hover:bg-gray-200 transition-colors ${
                            copiedMessageId === message.id ? 'text-green-600' : 'text-gray-400 hover:text-gray-600'
                          }`}
                          title={copiedMessageId === message.id ? 'Copied!' : 'Copy raw markdown'}
                        >
                          {copiedMessageId === message.id ? (
                            <Check className="h-3 w-3" />
                          ) : (
                            <Copy className="h-3 w-3" />
                          )}
                        </button>
                      )}
                    </div>
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
          <form onSubmit={handleSendMessage} className="flex flex-col gap-2 sm:flex-row">
            <textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={isEntryReady ? "Ask about the content..." : "Waiting for transcript..."}
              disabled={isLoading || !isEntryReady}
              rows={Math.min(Math.max(inputValue.split('\n').length, 2), 6)}
              className="flex-1 resize-y rounded-md border border-gray-300 px-3 py-2 focus:border-primary-500 focus:outline-none focus:ring-primary-500 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!inputValue.trim() || isLoading || !isEntryReady}
              className="self-end rounded-md bg-primary-600 px-4 py-2 text-white transition-colors hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-50 sm:self-auto"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
          
          {isEntryReady && messages.length <= 1 && (
            <div className="mt-4 space-y-4">
              <div>
                <p className="mb-2 text-xs text-gray-500">Quick fill</p>
                <div className="flex flex-wrap gap-2">
                  {suggestedQuestions.map((question, index) => (
                    <button
                      key={index}
                      onClick={() => handleQuestionClick(question)}
                      disabled={isLoading}
                      className="rounded-full border border-gray-200 bg-gray-100 px-3 py-1 text-xs text-gray-700 transition-colors hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {question}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-xs text-gray-500">Prompt templates</p>
                  {isLoadingTemplates && (
                    <span className="text-[11px] text-gray-400">Loading...</span>
                  )}
                </div>

                {promptTemplatesError && (
                  <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                    {promptTemplatesError}
                  </div>
                )}

                {!promptTemplatesError && promptTemplates.length > 0 && (
                  <div className="grid gap-3 md:grid-cols-2">
                    {promptTemplates.map((template) => (
                      <div
                        key={template.id}
                        className="rounded-xl border border-gray-200 bg-gray-50/70 p-3"
                      >
                        <div className="space-y-1">
                          <p className="font-medium text-gray-900">{template.label}</p>
                          <p className="text-sm text-gray-500">
                            {template.preview_text || 'Reusable markdown prompt'}
                          </p>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            onClick={() => setPreviewTemplate(template)}
                            disabled={isLoading}
                            aria-label={`Preview ${template.label}`}
                            className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Preview
                          </button>
                          <button
                            onClick={() => handleTemplateUse(template, false)}
                            disabled={isLoading}
                            aria-label={`Use Only ${template.label}`}
                            className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Use Only
                          </button>
                          <button
                            onClick={() => handleTemplateUse(template, true)}
                            disabled={isLoading}
                            aria-label={`Use & Send ${template.label}`}
                            className="rounded-md bg-primary-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Use &amp; Send
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {!promptTemplatesError && !isLoadingTemplates && promptTemplates.length === 0 && (
                  <p className="text-sm text-gray-500">No prompt templates are active yet.</p>
                )}
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

      <PromptTemplatePreviewModal
        bodyMarkdown={previewTemplate?.body_markdown ?? ''}
        isOpen={previewTemplate !== null}
        title={previewTemplate?.label ?? 'Prompt template preview'}
        onClose={() => setPreviewTemplate(null)}
      />
    </div>
  );
};

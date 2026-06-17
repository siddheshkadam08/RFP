import { Bot, Plus, Send, Sparkles, User2 } from 'lucide-react';
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';

import EmptyState from '@/components/common/EmptyState';
import { getApiErrorMessage, post } from '@/services/api';
import type { ChatMessage, ChatResponse } from '@/utils/types';

const suggestedPrompts = [
  'Show top opportunities in Asia',
  'Summarize new opportunities',
  'Which regions show growth?',
  'Compare two countries',
];

const CopilotPage = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const greeting = useMemo(
    () =>
      messages.length
        ? null
        : 'Ask the AI Copilot to summarize opportunity signals, compare markets, or identify the best-fit pursuits for your team.',
    [messages.length],
  );

  const submitMessage = async (message: string) => {
    if (!message.trim()) {
      return;
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: message.trim(),
      created_at: new Date().toISOString(),
      session_id: sessionId,
    };

    setMessages((current) => [...current, userMessage]);
    setInput('');
    setLoading(true);
    setError('');

    try {
      const response = await post<ChatResponse>('/ai/chat', {
        session_id: sessionId,
        message: message.trim(),
      });

      setSessionId(response.session_id);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: response.answer,
          created_at: new Date().toISOString(),
          citations: response.citations,
          confidence: response.confidence,
          session_id: response.session_id,
        },
      ]);
    } catch (submitError) {
      setError(getApiErrorMessage(submitError, 'Copilot is unavailable right now.'));
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: 'Copilot could not reach the live AI service. Please retry shortly or start a new chat session.',
          created_at: new Date().toISOString(),
          citations: [],
          confidence: 0.21,
          session_id: sessionId,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await submitMessage(input);
  };

  const startNewChat = () => {
    setMessages([]);
    setInput('');
    setSessionId(undefined);
    setError('');
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[0.95fr_2.05fr]">
      <aside className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-600">AI Workspace</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-900">Copilot Sessions</h2>
          </div>
          <button
            type="button"
            onClick={startNewChat}
            className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            New Chat
          </button>
        </div>

        <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-5">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-blue-50 p-2 text-blue-600">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-900">Suggested prompts</p>
              <div className="mt-4 space-y-2">
                {suggestedPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => void submitMessage(prompt)}
                    className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-600 transition hover:border-blue-200 hover:bg-blue-50/50 hover:text-slate-900"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </aside>

      <section className="flex h-[75vh] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-6 py-4">
          <h1 className="text-lg font-semibold text-slate-900">AI Copilot</h1>
          <p className="text-sm text-slate-500">Context-aware assistance for opportunity qualification, market comparisons, and pipeline insights.</p>
        </div>

        {error ? <div className="border-b border-rose-200 bg-rose-50 px-6 py-3 text-sm text-rose-700">{error}</div> : null}

        <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50 px-6 py-6">
          {greeting ? <EmptyState icon={Bot} title="Start a conversation" description={greeting} /> : null}

          {messages.map((message) => {
            const isUser = message.role === 'user';

            return (
              <div key={message.id} className={['flex', isUser ? 'justify-end' : 'justify-start'].join(' ')}>
                <div className={['max-w-3xl rounded-2xl px-5 py-4 shadow-sm', isUser ? 'bg-blue-600 text-white' : 'bg-white text-slate-800'].join(' ')}>
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] opacity-80">
                    {isUser ? <User2 className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                    {isUser ? 'You' : 'Assistant'}
                  </div>
                  <p className="text-sm leading-7">{message.content}</p>

                  {!isUser ? (
                    <div className="mt-4 space-y-3 border-t border-slate-100 pt-4 text-xs text-slate-500">
                      {typeof message.confidence === 'number' ? <p>Confidence: {(message.confidence * 100).toFixed(0)}%</p> : null}
                      {message.citations?.length ? (
                        <div className="space-y-2">
                          <p className="font-semibold uppercase tracking-[0.16em] text-slate-400">Citations</p>
                          {message.citations.map((citation, index) => (
                            <div key={`${citation.title}-${index}`} className="rounded-xl bg-slate-50 px-3 py-2">
                              <p className="font-medium text-slate-700">{citation.title ?? 'Reference'}</p>
                              {citation.snippet ? <p className="mt-1">{citation.snippet}</p> : null}
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })}

          {loading ? (
            <div className="flex justify-start">
              <div className="rounded-2xl bg-white px-5 py-4 text-sm text-slate-500 shadow-sm">Copilot is thinking…</div>
            </div>
          ) : null}

          <div ref={messagesEndRef} />
        </div>

        <form className="border-t border-slate-200 bg-white px-6 py-4" onSubmit={handleSubmit}>
          <div className="flex items-end gap-3">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              rows={2}
              placeholder="Ask about regions, trends, qualification logic, or pipeline strategy"
              className="min-h-[72px] flex-1 rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="inline-flex items-center gap-2 rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Send className="h-4 w-4" />
              Send
            </button>
          </div>
        </form>
      </section>
    </div>
  );
};

export default CopilotPage;

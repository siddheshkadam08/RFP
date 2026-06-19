import { get, post } from '@/services/api';
import type { ChatResponse, ChatSessionDetail, ChatSessionSummary } from '@/utils/types';

// Grounded RAG chat — POST /ai/chat returns { answer, citations[], confidence, session_id }.
export const sendChat = (sessionId: string | undefined, message: string) =>
  post<ChatResponse>('/ai/chat', { session_id: sessionId ?? null, message });

// History sidebar.
export const listSessions = () => get<ChatSessionSummary[]>('/ai/sessions');

export const getSession = (sessionId: string) => get<ChatSessionDetail>(`/ai/sessions/${sessionId}`);

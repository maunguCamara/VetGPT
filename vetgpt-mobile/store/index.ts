/**
 * vetgpt-mobile/store/index.ts
 *
 * Zustand global state:
 * - Auth (user, token, loading)
 * - Chat (messages, streaming state)
 * - App (online status, settings)
 */

import { create } from 'zustand';
import { User, Citation } from '../app/lib/api';


// ─── Types ────────────────────────────────────────────────────────────────────

export type MessageRole = 'user' | 'assistant' | 'system';

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  citations?: Citation[];
  disclaimer?: string;
  isStreaming?: boolean;
  isError?: boolean;
  timestamp: Date;
  latency_ms?: number;
}

// ─── Auth Store ───────────────────────────────────────────────────────────────

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  setUser: (user: User | null) => void;
  setLoading: (v: boolean) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,

  setUser: (user) => set({
    user,
    isAuthenticated: !!user,
    isLoading: false,
  }),

  setLoading: (isLoading) => set({ isLoading }),

  logout: () => set({
    user: null,
    isAuthenticated: false,
    isLoading: false,
  }),
}));

// ─── Chat Store ───────────────────────────────────────────────────────────────

interface ChatState {
  messages: Message[];
  isQuerying: boolean;
  currentSessionId: string;

  addMessage: (msg: Message) => void;
  updateLastMessage: (content: string, done?: boolean) => void;
  setQuerying: (v: boolean) => void;
  clearChat: () => void;
  newSession: () => void;
}

function generateId(): string {
  return Math.random().toString(36).slice(2, 11);
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isQuerying: false,
  currentSessionId: generateId(),

  addMessage: (msg) =>
    set((state) => ({ messages: [...state.messages, msg] })),

  updateLastMessage: (content, done = false) =>
    set((state) => {
      const messages = [...state.messages];
      const last = messages[messages.length - 1];
      if (last && last.role === 'assistant') {
        messages[messages.length - 1] = {
          ...last,
          content: last.content + content,
          isStreaming: !done,
        };
      }
      return { messages };
    }),

  setQuerying: (isQuerying) => set({ isQuerying }),

  clearChat: () => set({ messages: [] }),

  newSession: () => set({
    messages: [],
    currentSessionId: generateId(),
    isQuerying: false,
  }),
}));

// ─── App Store ────────────────────────────────────────────────────────────────

interface AppState {
  isOnline: boolean;
  hasLocalModel: boolean;
  filterSpecies: string | null;
  filterSource: string | null;
  preferredLanguage: string | null;  // ISO-639-1 or null = auto-detect

  setOnline: (v: boolean) => void;
  setHasLocalModel: (v: boolean) => void;
  setFilterSpecies: (v: string | null) => void;
  setFilterSource: (v: string | null) => void;
  setPreferredLanguage: (v: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  isOnline: true,
  hasLocalModel: false,
  filterSpecies: null,
  filterSource: null,
  preferredLanguage: null,   // null = auto-detect from query text

  setOnline: (isOnline) => set({ isOnline }),
  setHasLocalModel: (hasLocalModel) => set({ hasLocalModel }),
  setFilterSpecies: (filterSpecies) => set({ filterSpecies }),
  setFilterSource: (filterSource) => set({ filterSource }),
  setPreferredLanguage: (preferredLanguage) => set({ preferredLanguage }),
}));

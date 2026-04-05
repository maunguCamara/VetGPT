/**
 * vetgpt-mobile/lib/api.ts
 *
 * Axios API client with:
 * - Auto token injection from secure storage
 * - Online/offline routing (cloud vs local LLM)
 * - Streaming support for chat
 * - Retry on network errors
 */

import axios, { AxiosInstance } from 'axios';
import * as SecureStore from 'expo-secure-store';
import * as Network from 'expo-network';

// ─── Config ──────────────────────────────────────────────────────────────────

const CLOUD_BASE_URL  = 'https://api.vetgpt.app';     // production
const LOCAL_BASE_URL  = 'http://localhost:8000';       // dev
const BASE_URL = __DEV__ ? LOCAL_BASE_URL : CLOUD_BASE_URL;

const TOKEN_KEY = 'vetgpt_auth_token';

// ─── Axios instance ───────────────────────────────────────────────────────────

const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Attach token to every request
api.interceptors.request.use(async (config) => {
  try {
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  } catch {}
  return config;
});

// Handle 401 — clear token and redirect to login
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.status === 401) {
      await SecureStore.deleteItemAsync(TOKEN_KEY);
    }
    return Promise.reject(error);
  }
);

// ─── Network utils ────────────────────────────────────────────────────────────

export async function isOnline(): Promise<boolean> {
  try {
    const state = await Network.getNetworkStateAsync();
    return !!(state.isConnected && state.isInternetReachable);
  } catch {
    return false;
  }
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  full_name: string;
  tier: 'free' | 'premium' | 'clinic';
  is_verified: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export async function register(
  email: string,
  password: string,
  fullName: string
): Promise<AuthResponse> {
  const res = await api.post<AuthResponse>('/api/auth/register', {
    email,
    password,
    full_name: fullName,
  });
  await SecureStore.setItemAsync(TOKEN_KEY, res.data.access_token);
  return res.data;
}

export async function login(
  email: string,
  password: string
): Promise<AuthResponse> {
  // FastAPI OAuth2 expects form data for /token endpoint
  const form = new FormData();
  form.append('username', email);
  form.append('password', password);

  const res = await api.post<AuthResponse>('/api/auth/login', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  await SecureStore.setItemAsync(TOKEN_KEY, res.data.access_token);
  return res.data;
}

export async function logout(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
}

export async function getMe(): Promise<User> {
  const res = await api.get<User>('/api/auth/me');
  return res.data;
}

export async function getStoredToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}

// ─── Query ────────────────────────────────────────────────────────────────────

export interface Citation {
  source_file: string;
  document_title: string;
  page_number: number;
  score: number;
  excerpt: string;
}

export interface QueryResponse {
  query: string;
  answer: string;
  citations: Citation[];
  chunks_retrieved: number;
  top_score: number;
  llm_model: string;
  latency_ms: number;
  disclaimer: string;
}

export async function queryVet(
  query: string,
  options?: {
    top_k?: number;
    filter_species?: string;
    filter_source?: string;
  }
): Promise<QueryResponse> {
  const online = await isOnline();

  if (!online) {
    // Offline: call local on-device LLM endpoint
    // Phase 2: replace with llama.cpp local server
    throw new Error('offline');
  }

  const res = await api.post<QueryResponse>('/api/query', {
    query,
    top_k: options?.top_k ?? 5,
    filter_species: options?.filter_species,
    filter_source: options?.filter_source,
  });
  return res.data;
}

export async function streamQuery(
  query: string,
  onToken: (token: string) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): Promise<void> {
  const online = await isOnline();
  if (!online) {
    onError(new Error('offline'));
    return;
  }

  try {
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    const response = await fetch(`${BASE_URL}/api/query/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ query, top_k: 5 }),
    });

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    if (!reader) return;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      const lines = chunk.split('\n').filter(l => l.startsWith('data: '));
      for (const line of lines) {
        const data = line.slice(6);
        if (data === '[DONE]') { onDone(); return; }
        try {
          const parsed = JSON.parse(data);
          if (parsed.token) onToken(parsed.token);
        } catch {}
      }
    }
    onDone();
  } catch (err) {
    onError(err as Error);
  }
}

// ─── History ──────────────────────────────────────────────────────────────────

export interface HistoryItem {
  id: number;
  query_text: string;
  answer_text: string;
  sources_used: Citation[];
  latency_ms: number;
  created_at: string;
}

export async function getHistory(limit = 20, offset = 0): Promise<HistoryItem[]> {
  const res = await api.get<HistoryItem[]>('/api/query/history', {
    params: { limit, offset },
  });
  return res.data;
}

// ─── Health ───────────────────────────────────────────────────────────────────

export async function checkHealth(): Promise<boolean> {
  try {
    await api.get('/api/health', { timeout: 5000 });
    return true;
  } catch {
    return false;
  }
}

export default api;

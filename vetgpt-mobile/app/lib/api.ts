/**
 * vetgpt-mobile/lib/api.ts
 *
 * API client using native fetch — no axios dependency.
 * Handles: auth token injection, online/offline detection, streaming.
 */

import { setItem, getItem, deleteItem } from './storage';
import * as Network from 'expo-network';

// ─── Config ───────────────────────────────────────────────────────────────────

const CLOUD_BASE_URL = 'https://api.vetgpt.app';
const LOCAL_BASE_URL = 'http://localhost:8000';
export const BASE_URL = __DEV__ ? LOCAL_BASE_URL : CLOUD_BASE_URL;

const TOKEN_KEY = 'vetgpt_auth_token';
const DEFAULT_TIMEOUT_MS = 30000;

// ─── Types ────────────────────────────────────────────────────────────────────

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
  formatted_references: string[];
  chunks_retrieved: number;
  top_score: number;
  llm_model: string;
  latency_ms: number;
  disclaimer: string;
}

export interface HistoryItem {
  id: number;
  query_text: string;
  answer_text: string;
  sources_used: Citation[];
  latency_ms: number;
  created_at: string;
}

// ─── Token helpers ────────────────────────────────────────────────────────────

export async function getStoredToken(): Promise<string | null> {
  return getItem(TOKEN_KEY);
}

async function saveToken(token: string): Promise<void> {
  await setItem(TOKEN_KEY, token);
}

async function clearToken(): Promise<void> {
  await deleteItem(TOKEN_KEY);
}

// ─── Network ──────────────────────────────────────────────────────────────────

export async function isOnline(): Promise<boolean> {
  try {
    const state = await Network.getNetworkStateAsync();
    return !!(state.isConnected && state.isInternetReachable);
  } catch {
    return false;
  }
}

// ─── API Error ────────────────────────────────────────────────────────────────

export class APIError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'APIError';
  }
}

// ─── Core fetch wrapper ───────────────────────────────────────────────────────

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  body?: object;
  headers?: Record<string, string>;
  timeoutMs?: number;
  requiresAuth?: boolean;
}

async function request<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const {
    method = 'GET',
    body,
    headers = {},
    timeoutMs = DEFAULT_TIMEOUT_MS,
    requiresAuth = true,
  } = options;

  const finalHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    ...headers,
  };

  if (requiresAuth) {
    const token = await getStoredToken();
    if (token) finalHeaders['Authorization'] = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: finalHeaders,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }

  if (response.status === 401) {
    await clearToken();
    throw new APIError(401, 'Session expired. Please log in again.');
  }

  const contentType = response.headers.get('content-type') ?? '';
  const data = contentType.includes('application/json')
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail = (data as any)?.detail ?? `Request failed (${response.status})`;
    throw new APIError(response.status, detail);
  }

  return data as T;
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export async function register(
  email: string,
  password: string,
  fullName: string
): Promise<AuthResponse> {
  const res = await request<AuthResponse>('/api/auth/register', {
    method: 'POST',
    body: { email, password, full_name: fullName } as any,
    requiresAuth: false,
  });
  await saveToken(res.access_token);
  return res;
}

export async function login(
  email: string,
  password: string
): Promise<AuthResponse> {
  // FastAPI OAuth2 expects application/x-www-form-urlencoded
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: email, password }).toString(),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new APIError(response.status, data?.detail ?? 'Incorrect email or password.');
  }

  const res: AuthResponse = await response.json();
  await saveToken(res.access_token);
  return res;
}

export async function logout(): Promise<void> {
  await clearToken();
}

export async function getMe(): Promise<User> {
  return request<User>('/api/auth/me');
}

// ─── Query ────────────────────────────────────────────────────────────────────

export async function queryVet(
  query: string,
  options?: {
    top_k?: number;
    filter_species?: string;
    filter_source?: string;
  }
): Promise<QueryResponse> {
  if (!(await isOnline())) throw new APIError(0, 'offline');

  return request<QueryResponse>('/api/query', {
    method: 'POST',
    body: {
      query,
      top_k: options?.top_k ?? 5,
      filter_species: options?.filter_species ?? null,
      filter_source:  options?.filter_source  ?? null,
    } as any,
  });
}

export async function streamQuery(
  query: string,
  onToken: (token: string) => void,
  onDone: () => void,
  onError: (err: Error) => void
): Promise<void> {
  if (!(await isOnline())) {
    onError(new APIError(0, 'offline'));
    return;
  }

  const token = await getStoredToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  try {
    const response = await fetch(`${BASE_URL}/api/query/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ query, top_k: 5 }),
    });

    if (!response.ok || !response.body) {
      throw new APIError(response.status, 'Stream request failed');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const lines = decoder.decode(value, { stream: true }).split('\n');

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6).trim();
        if (data === '[DONE]') { onDone(); return; }
        try {
          const parsed = JSON.parse(data);
          if (parsed.token) onToken(parsed.token);
        } catch { /* skip malformed lines */ }
      }
    }
    onDone();
  } catch (err) {
    if ((err as Error).name !== 'AbortError') onError(err as Error);
  }
}

// ─── History ──────────────────────────────────────────────────────────────────

export async function getHistory(limit = 20, offset = 0): Promise<HistoryItem[]> {
  return request<HistoryItem[]>(`/api/query/history?limit=${limit}&offset=${offset}`);
}

// ─── Health ───────────────────────────────────────────────────────────────────

export async function checkHealth(): Promise<boolean> {
  try {
    await request('/api/health', { requiresAuth: false, timeoutMs: 5000 });
    return true;
  } catch {
    return false;
  }
}

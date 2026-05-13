/**
 * vetgpt-mobile/app/lib/api.ts
 * All backend API calls. Uses native fetch only.
 */

import { getItem, setItem, deleteItem } from './storage';
import { Platform } from 'react-native';

const CLOUD  = 'https://api.vetgpt.app';
const LOCAL  = 'http://localhost:8000';
export const BASE_URL = __DEV__ ? LOCAL : CLOUD;

const TOKEN_KEY = 'vetgpt_auth_token';

// ========== Types ==========
export interface User {
  id: string;
  email: string;
  full_name: string;
  tier: 'free' | 'premium' | 'clinic';
  is_verified: boolean;
  created_at: string;
}

export interface Citation {
  source_file: string;
  document_title: string;
  page_number: number;
  score: number;
  excerpt: string;
}

export type SupportedLanguage = 'en' | 'sw' | 'fr' | 'ar' | 'pt' | 'es' | 'zh';

export const LANGUAGE_LABELS: Record<string, string> = {
  en: 'English', sw: 'Kiswahili', fr: 'Français',
  ar: 'العربية', pt: 'Português',  es: 'Español', zh: '中文',
};

// ========== Token Helpers ==========
export async function getStoredToken(): Promise<string | null> {
  return getItem(TOKEN_KEY);
}

// ========== Core fetch wrapper ==========
async function req(path: string, opts: RequestInit = {}): Promise<any> {
  const token = await getStoredToken();
  const res = await fetch(`${BASE_URL}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers ?? {}),
    },
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error((d as any).detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ========== Auth ==========
export async function getMe(): Promise<User> {
  return req('/api/auth/me');
}

export async function loginUser(email: string, password: string): Promise<any> {
  const body = new URLSearchParams({ username: email, password });
  const res = await fetch(`${BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error((d as any).detail ?? 'Login failed');
  }
  const data = await res.json();
  await setItem(TOKEN_KEY, data.access_token);
  console.log('Token stored:', await getStoredToken());
  return data;
}

export async function isOnline(): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    const res = await fetch(`${BASE_URL}/api/health`, {
      method: 'HEAD',
      signal: controller.signal,
    });
    clearTimeout(timeout);
    return res.status < 500;
  } catch {
    if (Platform.OS === 'web') {
      return typeof navigator !== 'undefined' ? navigator.onLine : false;
    }
    return false;
  }
}

export async function register(email: string, password: string, fullName: string): Promise<any> {
  const data = await req('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, full_name: fullName }),
  });
  await setItem(TOKEN_KEY, data.access_token);
  return data;
}

export async function logout(): Promise<void> {
  await deleteItem(TOKEN_KEY);
}

// ========== Query ==========
export async function queryVet(query: string, opts: any = {}): Promise<any> {
  return req('/api/query', {
    method: 'POST',
    body: JSON.stringify({ query, ...opts }),
  });
}

export async function streamQuery(
  query: string,
  onToken: (t: string) => void,
  onDone?: () => void,
  onError?:(err: Error) => void,
): Promise<void> {
  const token = await getStoredToken();
  const res = await fetch(`${BASE_URL}/api/query/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ query }),
  });
  if (!res.ok || !res.body) {
    // Fall back to non-streaming
    const data = await queryVet(query);
    onToken(data.answer ?? '');
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onToken(decoder.decode(value, { stream: true }));
  }
}
export interface QueryResponse {
  query: string;
  answer: string;
  citations: Citation[];
  formatted_references: string;  // "[1] WikiVet — p.12\n[2] Merck — p.304"
  chunks_retrieved: number;
  top_score: number;
  llm_model: string;
  latency_ms: number;
  disclaimer: string;
}

// ========== Billing ==========
export async function createCheckout(tier: string): Promise<any> {
  return req('/api/billing/checkout', { method: 'POST', body: JSON.stringify({ tier }) });
}

export async function getSubscriptionStatus(): Promise<any> {
  return req('/api/billing/subscription');
}

// app/lib/api.ts
export async function openBillingPortal(): Promise<string> {
  const data = await req('/api/billing/portal', { method: 'POST' });
  return data.portal_url;
}
//Yet to create a backend endpoint fo this

// ========== Google Sign‑In ==========
export async function googleSignIn(idToken: string): Promise<any> {
  const res = await fetch(`${BASE_URL}/api/auth/google`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id_token: idToken }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error((d as any).detail ?? 'Google sign-in failed');
  }
  const data = await res.json();
  await setItem(TOKEN_KEY, data.access_token);
  return data;
}
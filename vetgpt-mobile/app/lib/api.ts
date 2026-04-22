/**
 * vetgpt-mobile/app/lib/api.ts
 * All backend API calls. Uses native fetch only.
 */
import { getItem, setItem, deleteItem } from './storage';

const CLOUD  = 'https://api.vetgpt.app';
const LOCAL  = 'http://localhost:8000';
export const BASE_URL = __DEV__ ? LOCAL : CLOUD;

const TOKEN_KEY = 'vetgpt_auth_token';

export async function getStoredToken(): Promise<string | null> {
  return getItem(TOKEN_KEY);
}

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

export async function getMe(): Promise<any> {
  return req('/api/auth/me');
}

export async function loginUser(email: string, password: string): Promise<any> {
  const body = new URLSearchParams({ username: email, password });
  const token = await getStoredToken();
  const res = await fetch(`${BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body.toString(),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error((d as any).detail ?? 'Login failed');
  }
  const data = await res.json();
  await setItem(TOKEN_KEY, data.access_token);
  return data;
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

export async function queryVet(query: string, opts: any = {}): Promise<any> {
  return req('/api/query', {
    method: 'POST',
    body: JSON.stringify({ query, ...opts }),
  });
}

export async function streamQuery(
  query: string,
  onToken: (t: string) => void,
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

export async function createCheckout(tier: string): Promise<any> {
  return req('/api/billing/checkout', { method: 'POST', body: JSON.stringify({ tier }) });
}

export async function getSubscriptionStatus(): Promise<any> {
  return req('/api/billing/subscription');
}

export const LANGUAGE_LABELS: Record<string, string> = {
  en: 'English', sw: 'Kiswahili', fr: 'Français',
  ar: 'العربية', pt: 'Português',  es: 'Español', zh: '中文',
};

// ─── Google Sign-In ────────────────────────────────────────────────────────────

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
  await setItem('vetgpt_auth_token', data.access_token);
  return data;
}
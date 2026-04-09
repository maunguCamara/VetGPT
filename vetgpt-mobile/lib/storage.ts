/**
 * vetgpt-mobile/lib/storage.ts
 *
 * Safe storage wrapper.
 * - Native (iOS/Android): uses expo-secure-store (encrypted keychain)
 * - Web/browser: falls back to in-memory storage
 *   SecureStore is not available on web — this prevents the
 *   "getValueWithKeyAsync is not a function" crash in Expo Go web.
 */

import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

// In-memory fallback for web
const memoryStore: Record<string, string> = {};

export async function setItem(key: string, value: string): Promise<void> {
  if (Platform.OS === 'web') {
    memoryStore[key] = value;
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

export async function getItem(key: string): Promise<string | null> {
  if (Platform.OS === 'web') {
    return memoryStore[key] ?? null;
  }
  return SecureStore.getItemAsync(key);
}

export async function deleteItem(key: string): Promise<void> {
  if (Platform.OS === 'web') {
    delete memoryStore[key];
    return;
  }
  await SecureStore.deleteItemAsync(key);
}

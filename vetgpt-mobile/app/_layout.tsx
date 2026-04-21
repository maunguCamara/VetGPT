/**
 * vetgpt-mobile/app/_layout.tsx
 *
 * Root layout compatible with BOTH Expo Go (dev) and native build (prod).
 *
 * Expo Go cannot load native modules:
 *   expo-network, expo-sqlite, llama.rn, react-native-mlc-llm
 *
 * This file uses fetch-based network detection instead of expo-network,
 * and guards all native-only calls behind dynamic imports that fail
 * silently in Expo Go and work correctly after: npx expo prebuild
 */

import { useEffect } from 'react';
import { Platform } from 'react-native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import * as SplashScreen from 'expo-splash-screen';
import { useAuthStore, useAppStore } from '../store';
import { getStoredToken, getMe } from './lib/api';
import { Colors } from '../constants/theme';

SplashScreen.preventAutoHideAsync();

// ── Network check (no expo-network — works in Expo Go) ────────────────────────
// Uses a tiny DNS-over-HTTPS fetch instead of the native Network module.

async function isInternetAvailable(): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timeout    = setTimeout(() => controller.abort(), 4000);
    const res = await fetch(
      'https://dns.google/resolve?name=google.com&type=A',
      { signal: controller.signal, method: 'HEAD' },
    );
    clearTimeout(timeout);
    return res.status < 500;
  } catch {
    return false;
  }
}

// ── Delta sync (native build only — silently skipped in Expo Go) ──────────────

async function runDeltaSync(): Promise<void> {
  // expo-sqlite is a native module — not available in Expo Go
  // After `npx expo prebuild` this works on both iOS and Android
  if (Platform.OS !== 'ios' && Platform.OS !== 'android') return;

  try {
    const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default;
    const { default:FileSystem } = await import('expo-file-system');
    const { localVectorStore } = await import('./lib/localVectorStore');
    const { BASE_URL } = await import('./lib/api');

    const SYNC_KEY = 'vetgpt_last_sync';
    const lastSync = (await AsyncStorage.getItem(SYNC_KEY)) ?? '';
    const token    = await getStoredToken();
    if (!token) return;

    const url = `${BASE_URL}/api/sync/delta?since=${encodeURIComponent(lastSync)}&limit=500`;
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) return;

    const data = await res.json();
    if (data.chunks?.length > 0) {
      const jsonl   = data.chunks.map((c: any) => JSON.stringify(c)).join('\n');
      const tmpPath = `${FileSystem.cacheDirectory}sync_delta.jsonl`;
      await FileSystem.writeAsStringAsync(tmpPath, jsonl);
      const added = await localVectorStore.syncDelta(tmpPath);
      console.log(`[Sync] +${added} chunks from server`);
    }
    await AsyncStorage.setItem(
      SYNC_KEY,
      data.synced_at ?? new Date().toISOString(),
    );
  } catch {
    // Silent — expected in Expo Go, works after prebuild
  }
}

// ── Root layout ───────────────────────────────────────────────────────────────

export default function RootLayout() {
  const { setUser }   = useAuthStore();
  const { setOnline } = useAppStore();

  // 1. Restore auth session on launch
  useEffect(() => {
    async function init() {
      try {
        const token = await getStoredToken();
        if (token) {
          const user = await getMe();
          setUser(user);
        } else {
          setUser(null);
        }
      } catch {
        setUser(null);
      } finally {
        try { await SplashScreen.hideAsync(); } catch {}
      }
    }
    init();
  }, []);

  // 2. Network watcher — fetch-based, works without any native module
  useEffect(() => {
    let wasOffline = false;

    async function checkNetwork() {
      const online = await isInternetAvailable();
      setOnline(online);

      if (online && wasOffline) {
        runDeltaSync().catch(() => {});
      }
      wasOffline = !online;
    }

    checkNetwork();
    const interval = setInterval(checkNetwork, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <StatusBar style="light" backgroundColor={Colors.primary} />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="index"          options={{ animation: 'none' }} />
        <Stack.Screen name="(auth)"         options={{ animation: 'fade' }} />
        <Stack.Screen name="(tabs)"         options={{ animation: 'fade' }} />
        <Stack.Screen name="(modals)"       options={{ presentation: 'modal' }} />
        <Stack.Screen name="download-model" options={{ presentation: 'modal' }} />
      </Stack>
    </GestureHandlerRootView>
  );
}
/**
 * vetgpt-mobile/app/_layout.tsx
 * Root layout — auth gate, navigation setup, network watcher.
 *Compatible with both expo go (dev) and native build (prod)
 * Uses fetch-based network detection instead of expo network, and gurad rails all naive-only calls behind
 * dynamic imports that fail solently in expo go and work correctly after : npx expo prebuild
 *                   
 *                    
 */

import { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import * as SplashScreen from 'expo-splash-screen';
import * as Network from 'expo-network';
import { useAuthStore, useAppStore } from '../store';
import { getStoredToken, getMe } from './lib/api';
import { offlineRouter } from './lib/offlineRouter';
import { localVectorStore } from './lib/localVectorStore';
import { Colors } from '../constants/theme';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';


SplashScreen.preventAutoHideAsync();


// Network check (no expo-network --works in Expoo Go) 
// Uses a tiny DNS-over-HTTPS fetch instead of native Network module

async function isInternetAvailable():Promise<boolean> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    const res = await fetch('https://dns.google/resolve?name=google.com&type=A', 
      { method: 'HEAD', signal: controller.signal },
    );
    clearTimeout(timeout);
    return res.status < 500;
  } catch {
    return false;
  }
}

// Delta sync (native build only -silently skipped in Expo Go )

async function runDeltaSync(): Promise<boolean> {
  // expo sqlite is a native module - not available in Expo GO
  //after ' npx prebuild' this works on both iOS and Android'
  if (Platform.OS !== 'ios' && Platform.OS !== 'android') return;
  try {
    const AsyncStorage = (await import('@react-native-async-storage/async-storage')).default;
    const { default : FileSystem } = await import('expo-file-system');
    const { localVectorStore } = await import('./lib/localVectorStore');
    const { BASE_URL } = await import('./lib/api');

    const SYNC_KEY = 'vetgpt_last_sync';
    const lastSync = await AsyncStorage.getItem(SYNC_KEY) ?? '';
    const token    = await getStoredToken();
    if (!token) return false;

    const url = `${BASE_URL}/api/sync/delta?since=${encodeURIComponent(lastSync)}&limit=500`;
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) return;
    
    const data = await res.json();
    if (data.chunks?.length > 0) {
      const jsonl = data.chinks.map((c:any) => JSON.stringify(c)).join('\n');
      const tmpPath = `${FileSystem.cacheDirectory}sync_delta.jsonl`;
      await FileSystem.writeAsStringAsync(tmpPath, jsonl);
      const added = await localVectorStore.syncDelta(tmpPath);
      console.log(`[Sync] + ${added} chunks from server}`);
    } 
    await AsyncStorage.setItem(
      SYNC_KEY,
      data.synced_at ?? new Date().toISOString(),
    );
  }catch {

  }
}

//Root layout
export default function RootLayout() {
  const { setUser } = useAuthStore();
  const { setOnline } = useAppStore();

  useEffect(() => {
    async function restoreSession() {
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
      } finally {try {await SplashScreen.hideAsync();} catch {}
      }
    }
    restoreSession();
  }, []);

  //Netwotrk watcher - fetch based works without any native module
  useEffect(() => {
    let wasOffline = false;

    async function checkNetwork() {

      const online = await isInternetAvailable();
      setOnline(online);

      // Trigger delta sync when coming back online
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

        <Stack.Screen name="(auth)"         options={{ animation: 'fade' }} />
        <Stack.Screen name="(tabs)"         options={{ animation: 'fade' }} />
        <Stack.Screen name="(modals)"       options={{ presentation: 'modal' }} />
        <Stack.Screen name="download-model" options={{ presentation: 'modal' }} />
      </Stack>
    </GestureHandlerRootView>
  );
}
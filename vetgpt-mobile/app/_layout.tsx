/**
 * vetgpt-mobile/app/_layout.tsx
 * Root layout — auth gate, navigation setup, network watcher.
 */

import { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import * as SplashScreen from 'expo-splash-screen';
import * as Network from 'expo-network';
import * as FileSystem from 'expo-file-system';
import { useAuthStore, useAppStore } from '../store';
import { getStoredToken, getMe, BASE_URL } from './lib/api';
import { offlineRouter } from './lib/offlineRouter';
import { Colors } from '../constants/theme';
import { localVectorStore } from './lib/localVectorStore';
import AsyncStorage from '@react-native-async-storage/async-storage';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const { setUser, setLoading } = useAuthStore();
  const { setOnline } = useAppStore();

  // ── Restore auth session on launch ───────────────────────────────────────
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
      } finally {
        // Initialise local inference engine if model already downloaded
        offlineRouter.init();
        SplashScreen.hideAsync();
      }
    }
    restoreSession();
  }, []);

  // ── Network status watcher ────────────────────────────────────────────────
  useEffect(() => {
    
    let wasOffline = false;
    async function checkNetwork() {
      const state = await Network.getNetworkStateAsync();
      const online = !!(state.isConnected && state.isInternetReachable);
      setOnline(online);

      //Trigger delta sync when coming back online after being offline
      if (online && wasOffline) {
        triggerDeltaSync();
      }
      wasOffline = !online;

    }
    
    async function triggerDeltaSync() {
      try {
        const SYNC_KEY = 'vetgpt_last_sync';
        const lastSync = await AsyncStorage.getItem(SYNC_KEY) ?? '';
        const token = await getStoredToken();
        if (!token) return;
        
        const url = `${BASE_URL}/api/sync/delta?since=${encodeURIComponent(lastSync)}&limit=500`;
        const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
        if (!res.ok) {
          const data = await res.json();
          if (data.chunks && data.chunks.length > 0) {
            //Write Delta chunks to local vector store
            const JSONL = data.chunks.map((c: any) => JSON.stringify(c)).join('\n');
            const tmpPath = FileSystem.cacheDirectory + 'sync_delta.jsonl';
            await FileSystem.writeAsStringAsync(tmpPath, JSONL);
            const added = await localVectorStore.syncDelta(tmpPath);
            console.log('[Sync] Added ${added} new chunks from delta sync');
          }
          await AsyncStorage.setItem(SYNC_KEY, data.synced_at ?? new Date().toISOString());
        }
      } catch (err) {
        console.error('[Sync]Delta sync failed:', err);
      }
    }
    checkNetwork();
    const interval = setInterval(checkNetwork, 10000);   // check every 10s
    return () => clearInterval(interval);
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <StatusBar style="light" backgroundColor={Colors.primary} />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(auth)"  options={{ animation: 'fade' }} />
        <Stack.Screen name="(tabs)"  options={{ animation: 'fade' }} />
        <Stack.Screen name="(modals)" options={{ presentation: 'modal', headerShown: false }} />
         <Stack.Screen name="download-model" options={{ presentation: 'modal', headerShown: false }} />
      </Stack>
    </GestureHandlerRootView>
  );
}

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
import { useAuthStore, useAppStore } from '../store';
import { getStoredToken, getMe } from '../app/lib/api';
import { offlineRouter } from '../app/lib/offlineRouter';
import { Colors } from '../constants/theme';

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
    let interval: ReturnType<typeof setInterval>;

    async function checkNetwork() {
      const state = await Network.getNetworkStateAsync();
      setOnline(!!(state.isConnected && state.isInternetReachable));
    }

    checkNetwork();
    interval = setInterval(checkNetwork, 10000);   // check every 10s
    return () => clearInterval(interval);
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <StatusBar style="light" backgroundColor={Colors.primary} />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="auth"  options={{ animation: 'fade' }} />
        <Stack.Screen name="tabs"  options={{ animation: 'fade' }} />
        <Stack.Screen name="(modals)" options={{ presentation: 'modal', headerShown: false }} />
         <Stack.Screen name="download-model" />
      </Stack>
    </GestureHandlerRootView>
  );
}

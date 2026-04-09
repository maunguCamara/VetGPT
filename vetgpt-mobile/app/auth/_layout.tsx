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
import { useAuthStore, useAppStore } from '..//store';
import { getStoredToken, getMe } from '..//lib/api';
import { offlineRouter } from '..//lib/offlineRouter';
import { Colors } from '../../constants/theme';

SplashScreen.preventAutoHideAsync();

export default function AuthLayout() {
  return <Stack screenOptions={{ headerShown: false }} />;
}

/**
 * vetgpt-mobile/auth/_layout.tsx
 * Root layout — auth gate, navigation setup, network watcher.
 */


import * as SplashScreen from 'expo-splash-screen';

SplashScreen.preventAutoHideAsync();

import { Stack } from 'expo-router';

export default function AuthLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen 
        name="login" 
        options={{ 
          title: 'Sign In',
          headerBackVisible: false  // Remove back button
        }} 
      />
      <Stack.Screen name="register" />
    </Stack>
  );
}
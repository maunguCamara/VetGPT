/**
 * vetgpt-mobile/app/auth/_layout.tsx
 * Root layout — auth gate, navigation setup, network watcher.
 */


import * as SplashScreen from 'expo-splash-screen';
import { Stack } from 'expo-router';

SplashScreen.preventAutoHideAsync();

export default function AuthLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen 
        name="login" 
        options={{ 
          title: 'Sign In',
       
        }} 
      />
      <Stack.Screen name="register" options={{ title: 'Create Account'}} />
      <Stack.Screen name="signin" options={{ title: 'Sign In'}} />
    </Stack>
  );
}
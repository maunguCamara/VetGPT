/**
 * vetgpt-mobile/app/auth/_layout.tsx
 * Root layout — auth gate, navigation setup, network watcher.
 */



import { Stack } from 'expo-router';


export default function AuthLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen 
        name="signin" 
        options={{ 
          title: 'Sign In',
          headerBackVisible: false,
       
        }} 
      />
           <Stack.Screen 
        name="register" 
        options={{ 
          title: 'Create Account',
          headerBackVisible: true
        }} 
      />

    </Stack>
  );
}
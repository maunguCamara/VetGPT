/**
 * vetgpt-mobile/app/index.tsx
 * Root redirect — sends users to chat if logged in, login if not.
 */
import { Redirect } from 'expo-router';
import { useAuthStore } from '../store';

export default function Index() {
  const { isAuthenticated, isLoading } = useAuthStore();
  if (isLoading) return null;
  return <Redirect href={isAuthenticated ? '/(tabs)/chat' : '/(auth)/signin'} />;
}

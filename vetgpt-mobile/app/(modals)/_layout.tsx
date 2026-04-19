/**
 * vetgpt-mobile/app/(modals)/_layout.tsx
 * Modal screens layout
 */

import { Stack } from 'expo-router';

export default function ModalsLayout() {
  return (
    <Stack screenOptions={{ 
      headerShown: false,
      presentation: 'modal',
    }}>
      <Stack.Screen name="plans" />
    </Stack>
  );
}
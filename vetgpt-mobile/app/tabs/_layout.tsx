import { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import * as SplashScreen from 'expo-splash-screen';
import * as Network from 'expo-network';
import { useAuthStore, useAppStore } from '../../store';
import { getStoredToken, getMe } from '../lib/api';
import { offlineRouter } from '../lib/offlineRouter';
import { Colors } from '../../constants/theme';
import { Tabs } from 'expo-router';


export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: Colors.primary,
        tabBarInactiveTintColor: Colors.textMuted,
        headerStyle: { backgroundColor: Colors.primary },
        headerTintColor: '#fff',
      }}
    >
      <Tabs.Screen
        name="chat"
        options={{
          title: 'Chat',
          //tabBarIcon: ({ color }) => ({ text: '💬', color }), // Simplified
        }}
      />
      <Tabs.Screen
        name="search"
        options={{
          title: 'Search',
          //tabBarIcon: ({ color }) => ({ text: '🔍', color }),
        }}
      />
      <Tabs.Screen
        name="manuals"
        options={{
          title: 'Manuals',
          //tabBarIcon: ({ color }) => ({ text: '📚', color }),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profile',
          //tabBarIcon: ({ color }) => ({ text: '👤', color }),
        }}
      />
    </Tabs>
  );
}
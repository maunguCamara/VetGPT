import { Colors, Typography } from '../../constants/theme';
import { Tabs, Redirect } from 'expo-router';
import { View, Text, StyleSheet } from 'react-native';
import { useAuthStore, useAppStore } from '..//store';



function TabIcon({ emoji, label, focused, premium }: {
  emoji: string; label: string; focused: boolean; premium?: boolean;
}) {
  return (
    <View style={styles.tabIcon}>
      <Text style={[styles.emoji, focused && styles.emojiFocused]}>{emoji}</Text>
      <Text style={[styles.tabLabel, focused && styles.tabLabelFocused]}>{label}</Text>
      {premium && <View style={styles.premiumDot} />}
    </View>
  );
}


export default function TabLayout() {
  const { isAuthenticated, isLoading } = useAuthStore();
  if (isLoading) return null;
  if (!isAuthenticated) return <Redirect href="/(auth)/login" />;
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: Colors.primary,
        tabBarInactiveTintColor: Colors.textMuted,
                tabBarStyle: {
          backgroundColor: Colors.surface,
          borderTopColor: Colors.border,
          height: 60,
          paddingBottom: 8,
        },
        tabBarLabelStyle: {
          ...Typography.caption,
          fontSize: 11,
        },
        headerStyle: { backgroundColor: Colors.primary },
        headerTintColor: '#fff',
                headerTitleStyle: {
          ...Typography.h3,
          color: '#fff',
        },
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
const styles = StyleSheet.create({
  tabBar: {
    backgroundColor: Colors.surface,
    borderTopColor: Colors.border,
    borderTopWidth: 1,
    height: 70,
    paddingBottom: 8,
    paddingTop: 6,
  },
  tabIcon: { alignItems: 'center', justifyContent: 'center' },
  emoji: { fontSize: 22, opacity: 0.45 },
  emojiFocused: { opacity: 1 },
  tabLabel: { ...Typography.caption, color: Colors.textMuted, marginTop: 2 },
  tabLabelFocused: { color: Colors.primary, fontWeight: '600' },
  premiumDot: {
    position: 'absolute', top: -1, right: -4,
    width: 6, height: 6, borderRadius: 3,
    backgroundColor: Colors.accent,
  },
});

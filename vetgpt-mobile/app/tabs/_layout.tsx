import { Colors, Typography } from '../../constants/theme';
import { Tabs } from 'expo-router';


export default function TabLayout() {
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
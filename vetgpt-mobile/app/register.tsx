/**
 * vetgpt-mobile/app/(auth)/register.tsx
 */

import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView, Alert,
} from 'react-native';
import { useState } from 'react';
import { router } from 'expo-router';
import { register } from '../../lib/api';
import { useAuthStore } from '../../store';
import { Colors, Spacing, Radius, Typography, Shadow } from '../../constants/theme';

export default function RegisterScreen() {
  const [name, setName]         = useState('');
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm]   = useState('');
  const [loading, setLoading]   = useState(false);
  const { setUser } = useAuthStore();

  async function handleRegister() {
    if (!name.trim() || !email.trim() || !password) {
      Alert.alert('Missing fields', 'Please fill in all fields.'); return;
    }
    if (password !== confirm) {
      Alert.alert('Password mismatch', 'Passwords do not match.'); return;
    }
    if (password.length < 8) {
      Alert.alert('Weak password', 'Password must be at least 8 characters.'); return;
    }

    setLoading(true);
    try {
      const res = await register(email.trim().toLowerCase(), password, name.trim());
      setUser(res.user);
      router.replace('/(tabs)/chat');
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Registration failed. Try again.';
      Alert.alert('Error', msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: Colors.primary }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">

        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.back}>
            <Text style={styles.backText}>← Back</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Create account</Text>
          <Text style={styles.subtitle}>Join VetGPT — free to start</Text>
        </View>

        <View style={styles.card}>
          {([
            ['Full name', name, setName, 'words', 'name', false],
            ['Email', email, setEmail, 'email-address', 'email', false],
            ['Password', password, setPassword, 'default', 'password', true],
            ['Confirm password', confirm, setConfirm, 'default', 'password', true],
          ] as const).map(([label, value, setter, keyboard, complete, secure]) => (
            <View key={label}>
              <Text style={styles.label}>{label}</Text>
              <TextInput
                style={styles.input}
                placeholder={label}
                placeholderTextColor={Colors.textMuted}
                value={value}
                onChangeText={setter as any}
                autoCapitalize={keyboard === 'words' ? 'words' : 'none'}
                keyboardType={keyboard as any}
                autoComplete={complete as any}
                secureTextEntry={secure}
              />
            </View>
          ))}

          <TouchableOpacity
            style={[styles.button, loading && { opacity: 0.6 }]}
            onPress={handleRegister}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading
              ? <ActivityIndicator color="#fff" />
              : <Text style={styles.buttonText}>Create account</Text>
            }
          </TouchableOpacity>

          <Text style={styles.terms}>
            By registering you agree to our Terms of Service and Privacy Policy.
          </Text>
        </View>

      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: Spacing.lg, paddingTop: 60 },
  header: { marginBottom: Spacing.lg },
  back: { marginBottom: Spacing.md },
  backText: { color: 'rgba(255,255,255,0.8)', ...Typography.body },
  title: { ...Typography.h2, color: '#fff' },
  subtitle: { ...Typography.body, color: 'rgba(255,255,255,0.75)', marginTop: 4 },
  card: {
    backgroundColor: Colors.surface,
    borderRadius: Radius.xl,
    padding: Spacing.lg,
    ...Shadow.lg,
  },
  label: { ...Typography.label, color: Colors.textSecondary, marginTop: Spacing.sm, marginBottom: Spacing.xs },
  input: {
    borderWidth: 1, borderColor: Colors.border,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing.md, paddingVertical: 13,
    ...Typography.body, color: Colors.textPrimary,
    backgroundColor: Colors.background,
  },
  button: {
    backgroundColor: Colors.primary, borderRadius: Radius.md,
    paddingVertical: 15, alignItems: 'center', marginTop: Spacing.lg,
  },
  buttonText: { ...Typography.h4, color: '#fff' },
  terms: { ...Typography.caption, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.md },
});

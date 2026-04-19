/**
 * vetgpt-mobile/app/(auth)/signin.tsx
 * Sign-in screen - login with email and password
 */

import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, KeyboardAvoidingView, Platform,
  ScrollView, Alert,
} from 'react-native';
import { useState } from 'react';
import { router } from 'expo-router';
import { login } from '../lib/api';
import { useAuthStore } from '../../store';
import { Colors, Spacing, Radius, Typography, Shadow } from '../../constants/theme';

// ─── Validation helpers ───────────────────────────────────────────────────────

function validateEmail(email: string): string | null {
  if (!email.trim()) return 'Email is required';
  const re = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  if (!re.test(email.trim())) return 'Enter a valid email address';
  if (email.length > 254) return 'Email is too long';
  return null;
}

function validatePassword(password: string): string | null {
  if (!password) return 'Password is required';
  if (password.length < 8) return 'Password must be at least 8 characters';
  if (password.length > 72) return 'Password must be under 72 characters';
  return null;
}

// ─── Field component ──────────────────────────────────────────────────────────

interface FieldProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  error?: string | null;
  placeholder?: string;
  secure?: boolean;
  keyboardType?: 'default' | 'email-address';
  autoCapitalize?: 'none' | 'words';
  maxLength?: number;
}

function Field({
  label, value, onChange, error, placeholder,
  secure = false, keyboardType = 'default',
  autoCapitalize = 'none', maxLength = 100,
}: FieldProps) {
  return (
    <View style={fieldStyles.wrapper}>
      <View style={fieldStyles.labelRow}>
        <Text style={fieldStyles.label}>{label}</Text>
      </View>
      <TextInput
        style={[fieldStyles.input, !!error && fieldStyles.inputError]}
        placeholder={placeholder ?? label}
        placeholderTextColor={Colors.textMuted}
        value={value}
        onChangeText={onChange}
        secureTextEntry={secure}
        keyboardType={keyboardType}
        autoCapitalize={autoCapitalize}
        autoCorrect={false}
        maxLength={maxLength}
      />
      {!!error && <Text style={fieldStyles.error}>{error}</Text>}
    </View>
  );
}

const fieldStyles = StyleSheet.create({
  wrapper: { marginBottom: Spacing.md },
  labelRow: { marginBottom: Spacing.xs },
  label: { ...Typography.label, color: Colors.textSecondary },
  input: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: Radius.md,
    paddingHorizontal: Spacing.md, paddingVertical: 13,
    ...Typography.body, color: Colors.textPrimary, backgroundColor: Colors.background,
  },
  inputError: { borderColor: Colors.error },
  error: { ...Typography.caption, color: Colors.error, marginTop: 4 },
});

// ─── Main Screen ──────────────────────────────────────────────────────────────

export default function SignInScreen() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<{ email?: string | null; password?: string | null }>({});

  const { setUser } = useAuthStore();

  function validate(): boolean {
    const newErrors = {
      email: validateEmail(email),
      password: validatePassword(password),
    };
    setErrors(newErrors);
    return !newErrors.email && !newErrors.password;
  }

  async function handleSignIn() {
    if (!validate()) return;

    setLoading(true);
    try {
      const res = await login(email.trim().toLowerCase(), password);
      setUser(res.user);
      // Use replace to remove signin from navigation stack
      router.replace('/(tabs)/chat');
    } catch (err: any) {
      const msg = err?.message ?? 'Login failed. Please check your credentials.';
      Alert.alert('Login failed', msg);
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
          {/* No back button here - user can use device back or go to register */}
          <Text style={styles.title}>Welcome Back</Text>
          <Text style={styles.subtitle}>Sign in to VetGPT</Text>
        </View>

        <View style={styles.card}>
          <Field
            label="Email"
            value={email}
            onChange={(v) => { setEmail(v); setErrors((e) => ({ ...e, email: null })); }}
            error={errors.email}
            placeholder="vet@clinic.com"
            keyboardType="email-address"
            maxLength={254}
            autoCapitalize="none"
          />

          <Field
            label="Password"
            value={password}
            onChange={(v) => { setPassword(v); setErrors((e) => ({ ...e, password: null })); }}
            error={errors.password}
            placeholder="Enter your password"
            secure
            maxLength={72}
          />

          <TouchableOpacity
            style={[styles.button, loading && { opacity: 0.6 }]}
            onPress={handleSignIn}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading
              ? <ActivityIndicator color="#fff" />
              : <Text style={styles.buttonText}>Sign In</Text>
            }
          </TouchableOpacity>

          <TouchableOpacity 
            onPress={() => router.push('/(auth)/register')} 
            style={styles.registerLink}
          >
            <Text style={styles.registerLinkText}>
              Don't have an account? <Text style={{ color: Colors.primary, fontWeight: '600' }}>Create one</Text>
            </Text>
          </TouchableOpacity>

          <Text style={styles.terms}>
            By signing in, you agree to our Terms of Service and Privacy Policy.
          </Text>
        </View>

      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: Spacing.lg, paddingTop: 80, paddingBottom: Spacing.xxl },
  header: { marginBottom: Spacing.xl, alignItems: 'center' },
  title: { ...Typography.h1, color: '#fff', textAlign: 'center' },
  subtitle: { ...Typography.body, color: 'rgba(255,255,255,0.75)', marginTop: 8, textAlign: 'center' },
  card: {
    backgroundColor: Colors.surface, borderRadius: Radius.xl,
    padding: Spacing.lg, ...Shadow.lg,
  },
  button: {
    backgroundColor: Colors.primary, borderRadius: Radius.md,
    paddingVertical: 15, alignItems: 'center', marginTop: Spacing.md,
  },
  buttonText: { ...Typography.h4, color: '#fff' },
  registerLink: { alignItems: 'center', marginTop: Spacing.md },
  registerLinkText: { ...Typography.bodySmall, color: Colors.textSecondary },
  terms: { ...Typography.caption, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.lg },
});
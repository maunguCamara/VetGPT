/**
 * vetgpt-mobile/app/(auth)/register.tsx
 * Register screen with full field validation, char limits, no-paste on confirm.
 */

import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, KeyboardAvoidingView, Platform,
  ScrollView, Alert,
} from 'react-native';
import { useState } from 'react';
import { router } from 'expo-router';
import { register } from '../lib/api';
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

function validateName(name: string): string | null {
  if (!name.trim()) return 'Full name is required';
  if (name.trim().length < 2) return 'Name must be at least 2 characters';
  if (name.trim().length > 80) return 'Name must be under 80 characters';
  const re = /^[a-zA-Z\s'\-\.]+$/;
  if (!re.test(name.trim())) return 'Name can only contain letters, spaces, hyphens and apostrophes';
  return null;
}

function validatePassword(password: string): string | null {
  if (!password) return 'Password is required';
  if (password.length < 8) return 'Password must be at least 8 characters';
  if (password.length > 72) return 'Password must be under 72 characters';
  if (!/[A-Z]/.test(password)) return 'Password must contain at least one uppercase letter';
  if (!/[0-9]/.test(password)) return 'Password must contain at least one number';
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
  noContextMenu?: boolean;   // disables long-press paste menu
}

function Field({
  label, value, onChange, error, placeholder,
  secure = false, keyboardType = 'default',
  autoCapitalize = 'none', maxLength = 100,
  noContextMenu = false,
}: FieldProps) {
  return (
    <View style={fieldStyles.wrapper}>
      <View style={fieldStyles.labelRow}>
        <Text style={fieldStyles.label}>{label}</Text>
        {maxLength && (
          <Text style={[
            fieldStyles.counter,
            value.length > maxLength * 0.9 && { color: Colors.warning },
          ]}>
            {value.length}/{maxLength}
          </Text>
        )}
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
        contextMenuHidden={noContextMenu}
        selectTextOnFocus={!noContextMenu}
      />
      {!!error && <Text style={fieldStyles.error}>{error}</Text>}
    </View>
  );
}

const fieldStyles = StyleSheet.create({
  wrapper: { marginBottom: Spacing.sm },
  labelRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: Spacing.xs },
  label: { ...Typography.label, color: Colors.textSecondary },
  counter: { ...Typography.caption, color: Colors.textMuted },
  input: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: Radius.md,
    paddingHorizontal: Spacing.md, paddingVertical: 13,
    ...Typography.body, color: Colors.textPrimary, backgroundColor: Colors.background,
  },
  inputError: { borderColor: Colors.error },
  error: { ...Typography.caption, color: Colors.error, marginTop: 4 },
});

// ─── Main Screen ──────────────────────────────────────────────────────────────

export default function RegisterScreen() {
  const [name, setName]         = useState('');
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm]   = useState('');
  const [loading, setLoading]   = useState(false);

  // Field-level errors
  const [errors, setErrors] = useState<Record<string, string | null>>({});

  const { setUser } = useAuthStore();

  function validate(): boolean {
    const newErrors: Record<string, string | null> = {
      name:     validateName(name),
      email:    validateEmail(email),
      password: validatePassword(password),
      confirm:  confirm !== password ? 'Passwords do not match' : null,
    };
    setErrors(newErrors);
    return Object.values(newErrors).every((e) => !e);
  }

  async function handleRegister() {
    if (!validate()) return;

    setLoading(true);
    try {
      const res = await register(email.trim().toLowerCase(), password, name.trim());
      setUser(res.user);
      router.replace('/(tabs)/chat');
    } catch (err: any) {
      const msg = err?.message ?? 'Registration failed. Please try again.';
      Alert.alert('Registration failed', msg);
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
            <Text style={styles.backText}>← Back to login</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Create account</Text>
          <Text style={styles.subtitle}>Join VetGPT — free to start</Text>
        </View>

        <View style={styles.card}>

          <Field
            label="Full name"
            value={name}
            onChange={(v) => { setName(v); setErrors((e) => ({ ...e, name: null })); }}
            error={errors.name}
            placeholder="Dr. Jane Smith"
            autoCapitalize="words"
            maxLength={80}
          />

          <Field
            label="Email"
            value={email}
            onChange={(v) => { setEmail(v); setErrors((e) => ({ ...e, email: null })); }}
            error={errors.email}
            placeholder="vet@clinic.com"
            keyboardType="email-address"
            maxLength={254}
          />

          <Field
            label="Password"
            value={password}
            onChange={(v) => { setPassword(v); setErrors((e) => ({ ...e, password: null })); }}
            error={errors.password}
            placeholder="Min 8 chars, 1 uppercase, 1 number"
            secure
            maxLength={72}
          />

          <Field
            label="Confirm password"
            value={confirm}
            onChange={(v) => { setConfirm(v); setErrors((e) => ({ ...e, confirm: null })); }}
            error={errors.confirm}
            placeholder="Re-enter your password"
            secure
            maxLength={72}
            noContextMenu   // disables paste
          />

          <View style={styles.passwordHints}>
            {[
              { rule: password.length >= 8, text: 'At least 8 characters' },
              { rule: /[A-Z]/.test(password), text: 'One uppercase letter' },
              { rule: /[0-9]/.test(password), text: 'One number' },
              { rule: password === confirm && confirm.length > 0, text: 'Passwords match' },
            ].map(({ rule, text }) => (
              <Text key={text} style={[styles.hint, rule && styles.hintMet]}>
                {rule ? '✓' : '○'} {text}
              </Text>
            ))}
          </View>

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

          <TouchableOpacity onPress={() => router.back()} style={styles.loginLink}>
            <Text style={styles.loginLinkText}>
              Already have an account? <Text style={{ color: Colors.primary, fontWeight: '600' }}>Sign in</Text>
            </Text>
          </TouchableOpacity>

          <Text style={styles.terms}>
            By creating an account you agree to our Terms of Service and Privacy Policy.
          </Text>
        </View>

      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: Spacing.lg, paddingTop: 60, paddingBottom: Spacing.xxl },
  header: { marginBottom: Spacing.lg },
  back: { marginBottom: Spacing.md },
  backText: { color: 'rgba(255,255,255,0.8)', ...Typography.body },
  title: { ...Typography.h2, color: '#fff' },
  subtitle: { ...Typography.body, color: 'rgba(255,255,255,0.75)', marginTop: 4 },
  card: {
    backgroundColor: Colors.surface, borderRadius: Radius.xl,
    padding: Spacing.lg, ...Shadow.lg,
  },
  passwordHints: {
    backgroundColor: Colors.background, borderRadius: Radius.md,
    padding: Spacing.md, marginBottom: Spacing.md, gap: 4,
  },
  hint: { ...Typography.caption, color: Colors.textMuted },
  hintMet: { color: Colors.success },
  button: {
    backgroundColor: Colors.primary, borderRadius: Radius.md,
    paddingVertical: 15, alignItems: 'center', marginTop: Spacing.sm,
  },
  buttonText: { ...Typography.h4, color: '#fff' },
  loginLink: { alignItems: 'center', marginTop: Spacing.md },
  loginLinkText: { ...Typography.bodySmall, color: Colors.textSecondary },
  terms: { ...Typography.caption, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.md },
});

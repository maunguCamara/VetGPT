/**
 * vetgpt-mobile/app/(auth)/login.tsx
 *
 * Sign-in screen with:
 *   - Email + password login (FastAPI OAuth2)
 *   - Google Sign-In (OAuth 2.0 via expo-auth-session)
 *
 * Security:
 *   - Passwords sent over HTTPS only, never stored
 *   - Token stored in SecureStore (iOS Keychain / Android Keystore)
 *   - Google ID token verified server-side against Google's public keys
 *   - No Google password ever touches our server
 */

import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, KeyboardAvoidingView, Platform,
  Alert, ScrollView,
} from 'react-native';
import { useState, useEffect, useRef } from 'react';
import { router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import * as AuthSession from 'expo-auth-session';
import * as Google from 'expo-auth-session/providers/google';
import { loginUser, googleSignIn, register } from '../lib/api';
import { useAuthStore } from '../../store';
import { Colors, Spacing, Radius, Typography, Shadow } from '../../constants/theme';

// Required for expo-auth-session to close the browser after OAuth
WebBrowser.maybeCompleteAuthSession();

// ── Your Google OAuth Client IDs ─────────────────────────────────────────────
// Get from: console.cloud.google.com → APIs & Services → Credentials
// Replace these placeholders with your real IDs before production build.
const GOOGLE_CLIENT_IDS = {
  iosClientId:     process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID     ?? '',
  androidClientId: process.env.EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID ?? '',
  webClientId:     process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID     ?? '',
};

const GOOGLE_CONFIGURED = Object.values(GOOGLE_CLIENT_IDS).some(Boolean);

// ─────────────────────────────────────────────────────────────────────────────

export default function LoginScreen() {
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading]   = useState(false);
  const [gLoading, setGLoading] = useState(false);
  const { setUser, isAuthenticated } = useAuthStore();
   const hasNavigated = useRef(false);
  // Google OAuth hook
  const [request, response, promptAsync] = Google.useAuthRequest(GOOGLE_CLIENT_IDS);

    //useEffect(() => {
   // if (isAuthenticated && !hasNavigated.current) {
    //  hasNavigated.current = true;
   //   router.replace('/(tabs)/chat');
   // }
  //}, [isAuthenticated]);
  // Handle Google OAuth response
  useEffect(() => {
    if (response?.type === 'success') {
      const idToken = response.authentication?.idToken;
      if (idToken) handleGoogleToken(idToken);
      else setGLoading(false);
    } else if (response?.type === 'error') {
      setGLoading(false);
      Alert.alert('Google Sign-In failed', response.error?.message ?? 'Try again.');
    } else if (response?.type === 'dismiss') {
      setGLoading(false);
    }
  }, [response]);

  async function fetchGoogleIdToken(accessToken: string) {
    try {
      const res  = await fetch(
        `https://oauth2.googleapis.com/tokeninfo?access_token=${accessToken}`
      );
      const data = await res.json();
      if (data.email) {
        // Use access token as ID token for verification
        await handleGoogleToken(accessToken);
      }
    } catch {
      setGLoading(false);
      Alert.alert('Google Sign-In failed', 'Could not retrieve account info.');
    }
  }

  async function handleGoogleToken(idToken: string) {
    setGLoading(true);
    try {
      const data = await googleSignIn(idToken);
      //API returns {access_token, user: {id, email, fullname, tier
      setUser(data.user);
      setTimeout(() => router.replace('/(tabs)/chat'), 100);
    } catch (err: any) {
      Alert.alert(
        'Google Sign-In failed',
        err.message ?? 'Could not sign in with Google. Try email/password.',
      );
    } finally {
      setGLoading(false);
    }
  }

  async function handleGooglePress() {
    if (!GOOGLE_CONFIGURED) {
      Alert.alert(
        'Google Sign-In not configured',
        'Add your Google Client IDs to your .env file.\n\n' +
        'EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID=...\n' +
        'EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID=...',
      );
      return;
    }
    setGLoading(true);
    await promptAsync();
    // gLoading is set to false in the useEffect above
  }

  async function handleEmailLogin() {
    const emailTrimmed = email.trim().toLowerCase();
    if (!emailTrimmed || !password) {
      Alert.alert('Missing fields', 'Enter your email and password.');
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(emailTrimmed)) {
      Alert.alert('Invalid email', 'Enter a valid email address.');
      return;
    }
    setLoading(true);
    try {
      const data = await loginUser(emailTrimmed, password);
      setUser(data.user);
      setTimeout(() => router.replace('/(tabs)/chat'), 100);
    } catch (err: any) {
      const msg = err.message ?? '';
      if (msg.includes('401') || msg.includes('Incorrect')) {
        Alert.alert('Login failed', 'Incorrect email or password.');
      } else if (msg.includes('network') || msg.includes('fetch')) {
        Alert.alert('Connection error', 'Could not reach the server. Check your internet connection.');
      } else {
        Alert.alert('Login failed', msg || 'Something went wrong. Try again.');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: Colors.primary }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        contentContainerStyle={s.container}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* Hero */}
        <View style={s.hero}>
          <Text style={s.logo}>🐾</Text>
          <Text style={s.appName}>VetGPT</Text>
          <Text style={s.tagline}>AI veterinary reference</Text>
        </View>

        <View style={s.card}>

          {/* Google Sign-In */}
          <TouchableOpacity
            style={[s.googleBtn, (gLoading || !request) && s.btnDisabled]}
            onPress={handleGooglePress}
            disabled={gLoading || !request}
            activeOpacity={0.85}
          >
            {gLoading ? (
              <ActivityIndicator color={Colors.textPrimary} />
            ) : (
              <>
                <Text style={s.googleIcon}>G</Text>
                <Text style={s.googleBtnText}>Continue with Google</Text>
              </>
            )}
          </TouchableOpacity>

          {/* Divider */}
          <View style={s.divider}>
            <View style={s.dividerLine} />
            <Text style={s.dividerText}>or sign in with email</Text>
            <View style={s.dividerLine} />
          </View>

          {/* Email field */}
          <Text style={s.label}>Email</Text>
          <TextInput
            style={s.input}
            placeholder="vet@clinic.com"
            placeholderTextColor={Colors.textMuted}
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            returnKeyType="next"
          />

          {/* Password field */}
          <Text style={s.label}>Password</Text>
          <TextInput
            style={s.input}
            placeholder="Your password"
            placeholderTextColor={Colors.textMuted}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="password"
            returnKeyType="done"
            onSubmitEditing={handleEmailLogin}
          />

          {/* Sign in button */}
          <TouchableOpacity
            style={[s.signInBtn, loading && s.btnDisabled]}
            onPress={handleEmailLogin}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading
              ? <ActivityIndicator color="#fff" />
              : <Text style={s.signInBtnText}>Sign in</Text>
            }
          </TouchableOpacity>

          {/* Register link */}
          <TouchableOpacity
            style={s.registerLink}
            onPress={() => router.push('/(auth)/register')}
            activeOpacity={0.7}
          >
            <Text style={s.registerLinkText}>
              No account?{' '}
              <Text style={{ color: Colors.primary, fontWeight: '600' }}>
                Create one free
              </Text>
            </Text>
          </TouchableOpacity>

        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  container:   { flexGrow: 1, padding: Spacing.lg, paddingTop: 70, paddingBottom: 40 },

  hero:        { alignItems: 'center', marginBottom: Spacing.xl },
  logo:        { fontSize: 64 },
  appName:     { ...Typography.h1, color: '#fff', marginTop: Spacing.sm },
  tagline:     { ...Typography.body, color: 'rgba(255,255,255,0.75)', marginTop: 4 },

  card:        {
    backgroundColor: Colors.surface,
    borderRadius: Radius.xl,
    padding: Spacing.lg,
    ...Shadow.lg,
  },

  googleBtn:   {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#fff',
    borderRadius: Radius.md, paddingVertical: 14,
    borderWidth: 1, borderColor: Colors.border,
    gap: Spacing.sm,
    ...Shadow.sm,
  },
  googleIcon:  { fontSize: 18, fontWeight: '700', color: '#4285F4' },
  googleBtnText: { ...Typography.h4, color: Colors.textPrimary },

  divider:     { flexDirection: 'row', alignItems: 'center', marginVertical: Spacing.md, gap: Spacing.sm },
  dividerLine: { flex: 1, height: 1, backgroundColor: Colors.border },
  dividerText: { ...Typography.caption, color: Colors.textMuted },

  label:       { ...Typography.label, color: Colors.textSecondary, marginBottom: 6 },
  input:       {
    borderWidth: 1, borderColor: Colors.border,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Platform.OS === 'ios' ? 14 : 11,
    ...Typography.body, color: Colors.textPrimary,
    marginBottom: Spacing.md,
  },

  signInBtn:   {
    backgroundColor: Colors.primary,
    borderRadius: Radius.md,
    paddingVertical: 15,
    alignItems: 'center',
    marginTop: Spacing.xs,
    ...Shadow.sm,
  },
  signInBtnText: { ...Typography.h4, color: '#fff' },

  btnDisabled:  { opacity: 0.55 },

  registerLink: { alignItems: 'center', marginTop: Spacing.md, paddingVertical: 6 },
  registerLinkText: { ...Typography.body, color: Colors.textSecondary },

  securityNote: {
    ...Typography.caption, color: 'rgba(255,255,255,0.6)',
    textAlign: 'center', marginTop: Spacing.lg,
  },
});
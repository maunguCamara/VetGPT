/**
 * vetgpt-mobile/app/(tabs)/profile.tsx
 * User profile, subscription tier, settings and logout.
 */

import {
  View, Text, TouchableOpacity, StyleSheet,
  ScrollView, SafeAreaView, Alert, Switch,
} from 'react-native';
import { useState } from 'react';
import { router } from 'expo-router';
import { login, logout } from '../lib/api';
import { Colors, Spacing, Radius, Typography, Shadow } from '../constants/theme';
import { useAuthStore, useAppStore } from '../store';

function TierBadge({ tier }: { tier: string }) {
  const isPremium = tier === 'premium' || tier === 'clinic';
  return (
    <View style={[styles.tierBadge, isPremium && styles.tierBadgePremium]}>
      <Text style={[styles.tierText, isPremium && styles.tierTextPremium]}>
        {isPremium ? '⭐ ' : ''}{tier.charAt(0).toUpperCase() + tier.slice(1)}
      </Text>
    </View>
  );
}

function SettingRow({
  label, sub, value, onToggle,
}: { label: string; sub?: string; value: boolean; onToggle: (v: boolean) => void }) {
  return (
    <View style={styles.settingRow}>
      <View style={styles.settingText}>
        <Text style={styles.settingLabel}>{label}</Text>
        {sub && <Text style={styles.settingSub}>{sub}</Text>}
      </View>
      <Switch
        value={value}
        onValueChange={onToggle}
        trackColor={{ true: Colors.primary, false: Colors.borderStrong }}
        thumbColor="#fff"
      />
    </View>
  );
}

export default function ProfileScreen() {
  const { user, isAuthenticated, logout, logout: storeLogout } = useAuthStore();
  const { isOnline, filterSpecies, setFilterSpecies } = useAppStore();
  const [streamingEnabled, setStreamingEnabled] = useState(true);
  const [citationsEnabled, setCitationsEnabled] = useState(true);
  const [hasLocalModel, setHasLocalModel] = useState(false);
  const showSignOut = isAuthenticated && user !== null;

  const isPremium = user?.tier === 'premium' || user?.tier === 'clinic';
  const speciesOptions = ['None', 'Canine', 'Feline', 'Equine', 'Bovine'];

  async function handleLogout() {
    Alert.alert('Sign out', 'Are you sure you want to sign out?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Sign out',
        style: 'destructive',
        onPress: async () => {
          await logout();
          storeLogout();
          router.replace('/(auth)/login');
        },
      },
    ]);
  }

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.title}>Profile</Text>
      </View>

      <ScrollView contentContainerStyle={styles.content}>

        {/* User card */}
        <View style={styles.userCard}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>
              {user?.full_name?.charAt(0)?.toUpperCase() ?? '?'}
            </Text>
          </View>
          <View style={styles.userInfo}>
            <Text style={styles.userName}>{user?.full_name || 'Veterinarian'}</Text>
            <Text style={styles.userEmail}>{user?.email}</Text>
          </View>
          {user?.tier && <TierBadge tier={user.tier} />}
        </View>

        {/* Status */}
        <View style={styles.statusRow}>
          <View style={[styles.statusDot, { backgroundColor: isOnline ? Colors.online : Colors.offline }]} />
          <Text style={styles.statusText}>{isOnline ? 'Online — Cloud AI active' : 'Offline'}</Text>
        </View>

        {/* Upgrade banner for free users */}
        {!isPremium && (
          <View style={styles.upgradeBanner}>
            <Text style={styles.upgradeTitle}>⭐ Upgrade to Premium</Text>
            <Text style={styles.upgradeSub}>
              Unlock X-ray analysis, image recognition, advanced OCR and more.
            </Text>
            <TouchableOpacity style={styles.upgradeBtn}>
              <Text style={styles.upgradeBtnText}>View plans →</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Settings */}
        <Text style={styles.sectionLabel}>Settings</Text>

        <View style={styles.settingsCard}>
          <SettingRow
            label="Streaming responses"
            sub="Show answers word by word as they generate"
            value={streamingEnabled}
            onToggle={setStreamingEnabled}
          />
          <View style={styles.divider} />
          <SettingRow
            label="Show citations"
            sub="Display source references below each answer"
            value={citationsEnabled}
            onToggle={setCitationsEnabled}
          />
        </View>

        {/* Species filter */}
        <Text style={styles.sectionLabel}>Default species filter</Text>
        <View style={styles.speciesGrid}>
          {speciesOptions.map((s) => {
            const isActive = filterSpecies === s.toLowercAse() || (s === 'None' && !filterSpecies);
            return (
              <TouchableOpacity
                key={s}
                style={[styles.speciesChip, isActive && styles.speciesChipActive]}
                onPress={() => setFilterSpecies(s === 'None' ? '' : s.toLowerCase())}
              >
                <Text style={[
                  styles.speciesChipText,
                  isActive && styles.speciesChipTextActive,
                ]}>
                  {s}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {/* Phase 2: Download offline model */}
        <Text style={styles.sectionLabel}>Offline Model (Phase 2)</Text>
        <View style={styles.offlineCard}>
          <Text style={styles.offlineTitle}>Qwen2.5-3B (1.8 GB)</Text>
          <Text style={styles.offlineSub}>
            Download once, use VetGPT without internet.
            Requires Wi-Fi and 2 GB free storage.
          </Text>
          <TouchableOpacity style={styles.downloadBtn} onPress={() => router.push('/download-model')}>
            <Text style={styles.downloadBtnText}>
              {hasLocalModel ? 'Model ready — tap to manage' : 'Download offline model (1.93 GB)'}
            </Text>
          </TouchableOpacity>
        </View>

        {/* Logout */}
        

        <Text style={styles.version}>VetGPT v1.0.0</Text>
         {showSignOut && (
        <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
          <Text style={styles.logoutText}>Sign out</Text>
        </TouchableOpacity>
      )}
      {!showSignOut && (
        <TouchableOpacity style={styles.logoutBtn} onPress={() => router.push('/app/(auth)/signin')}>
          <Text style={styles.loginText}>Sign In</Text>
        </TouchableOpacity>
      )}
      </ScrollView>
     
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary,
    padding: Spacing.md,
    paddingTop: Spacing.lg,
  },
  title: { ...Typography.h3, color: '#fff' },
  content: { padding: Spacing.md, paddingBottom: Spacing.xxl },

  userCard: {
    backgroundColor: Colors.surface,
    borderRadius: Radius.lg,
    padding: Spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    marginBottom: Spacing.sm,
    ...Shadow.sm,
  },
  avatar: {
    width: 52, height: 52, borderRadius: 26,
    backgroundColor: Colors.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  avatarText: { ...Typography.h3, color: '#fff' },
  userInfo: { flex: 1 },
  userName: { ...Typography.h4, color: Colors.textPrimary },
  userEmail: { ...Typography.caption, color: Colors.textMuted },

  tierBadge: {
    backgroundColor: Colors.surfaceAlt,
    borderRadius: Radius.full,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 4,
  },
  tierBadgePremium: { backgroundColor: Colors.premiumBg },
  tierText: { ...Typography.caption, color: Colors.textSecondary, fontWeight: '700' },
  tierTextPremium: { color: Colors.accent },

  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: Spacing.md,
    paddingHorizontal: 4,
  },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { ...Typography.caption, color: Colors.textSecondary },

  upgradeBanner: {
    backgroundColor: Colors.premiumBg,
    borderRadius: Radius.lg,
    padding: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.accent + '44',
    marginBottom: Spacing.md,
  },
  upgradeTitle: { ...Typography.h4, color: Colors.accent },
  upgradeSub: { ...Typography.bodySmall, color: Colors.textSecondary, marginTop: 4 },
  upgradeBtn: {
    marginTop: Spacing.sm,
    backgroundColor: Colors.accent,
    borderRadius: Radius.md,
    paddingVertical: 8,
    paddingHorizontal: Spacing.md,
    alignSelf: 'flex-start',
  },
  upgradeBtnText: { ...Typography.label, color: '#fff' },

  sectionLabel: {
    ...Typography.label,
    color: Colors.textMuted,
    marginTop: Spacing.lg,
    marginBottom: Spacing.sm,
  },

  settingsCard: {
    backgroundColor: Colors.surface,
    borderRadius: Radius.lg,
    paddingHorizontal: Spacing.md,
    ...Shadow.sm,
  },
  settingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: Spacing.md,
  },
  settingText: { flex: 1 },
  settingLabel: { ...Typography.body, color: Colors.textPrimary },
  settingSub: { ...Typography.caption, color: Colors.textMuted, marginTop: 2 },
  divider: { height: 1, backgroundColor: Colors.divider },

  speciesGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.sm,
  },
  speciesChip: {
    borderRadius: Radius.full,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingHorizontal: Spacing.md,
    paddingVertical: 6,
    backgroundColor: Colors.surface,
  },
  speciesChipActive: { backgroundColor: Colors.primary, borderColor: Colors.primary },
  speciesChipText: { ...Typography.label, color: Colors.textSecondary },
  speciesChipTextActive: { color: '#fff' },

  offlineCard: {
    backgroundColor: Colors.surface,
    borderRadius: Radius.lg,
    padding: Spacing.md,
    ...Shadow.sm,
  },
  offlineTitle: { ...Typography.h4, color: Colors.textPrimary },
  offlineSub: { ...Typography.bodySmall, color: Colors.textSecondary, marginTop: 4 },
  downloadBtn: {
    marginTop: Spacing.sm,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radius.md,
    paddingVertical: 8,
    paddingHorizontal: Spacing.md,
    alignSelf: 'flex-start',
  },
  downloadBtnText: { ...Typography.label, color: Colors.textSecondary },

  logoutBtn: {
    marginTop: Spacing.xl,
    borderWidth: 1,
    borderColor: Colors.error,
    borderRadius: Radius.md,
    padding: Spacing.md,
    alignItems: 'center',
  },
  logoutText: { ...Typography.h4, color: Colors.error },
  loginText: { ...Typography.h4, color: Colors.primary },

  version: {
    ...Typography.caption,
    color: Colors.textMuted,
    textAlign: 'center',
    marginTop: Spacing.lg,
  },
});

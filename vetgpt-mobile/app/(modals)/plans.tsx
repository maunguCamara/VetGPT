/**
 * vetgpt-mobile/app/(modals)/plans.tsx
 * Subscription plans with live Stripe billing.
 */
import {
  View, Text, StyleSheet, TouchableOpacity,
  SafeAreaView, ScrollView, ActivityIndicator,
  Alert, Linking,
} from 'react-native';
import { useState } from 'react';
import { router } from 'expo-router';
import { createCheckout, openBillingPortal } from '../lib/api';
import { useAuthStore } from '../../store';
import { Colors, Spacing, Radius, Typography, Shadow } from '../../constants/theme';

const PLANS = [
  {
    key:     'free' as const,
    name:    'Free',
    price:   '$0',
    period:  'forever',
    color:   Colors.textSecondary,
    features: [
      '5 queries/min (unauth) · 20 queries/min (free)',
      'WikiVet, PubMed, FAO, eClinPath',
      'RAG chat with inline citations',
      'Manual browser & PDF upload',
      'Offline model download',
    ],
    cta:     'Current plan',
    accent:  false,
  },
  {
    key:     'premium' as const,
    name:    'Premium',
    price:   '$9.99',
    period:  '/month',
    color:   Colors.accent,
    features: [
      '100 queries/minute',
      'All open-access sources',
      '🩹 Wound assessment & classification',
      '🔬 Skin/lesion differential diagnosis',
      '🦟 Parasite identification',
      '🧫 Cytology slide interpretation',
      '🩻 X-ray & DICOM radiograph analysis',
      '📄 OCR — extract text from images',
    ],
    cta:     'Upgrade to Premium',
    accent:  true,
  },
  {
    key:     'clinic' as const,
    name:    'Clinic',
    price:   '$49.99',
    period:  '/month',
    color:   Colors.primary,
    features: [
      '500 queries/minute',
      'Everything in Premium',
      'Multi-seat access',
      'Admin analytics dashboard',
      'Fine-tuning data export',
      'Priority support',
    ],
    cta:     'Upgrade to Clinic',
    accent:  false,
  },
];

export default function PlansModal() {
  const { user } = useAuthStore();
  const [loading, setLoading] = useState<string | null>(null);

  async function handleUpgrade(tier: 'premium' | 'clinic') {
    if (!user) {
      Alert.alert('Sign in required', 'Please sign in to upgrade.', [
        { text: 'Cancel' },
        { text: 'Sign in', onPress: () => { router.back(); router.push('/(auth)/signin'); } },
      ]);
      return;
    }

    setLoading(tier);
    try {
      const { checkout_url } = await createCheckout(tier);
      // Open Stripe Checkout in the default browser
      const canOpen = await Linking.canOpenURL(checkout_url);
      if (canOpen) {
        await Linking.openURL(checkout_url);
        router.back();
      } else {
        Alert.alert('Error', 'Could not open the payment page. Try again later.');
      }
    } catch (err: any) {
      Alert.alert(
        'Checkout failed',
        err.message?.includes('not configured')
          ? 'Billing is not yet configured. Contact support.'
          : err.message ?? 'Something went wrong. Try again.',
      );
    } finally {
      setLoading(null);
    }
  }

  async function handleManageSubscription() {
    setLoading('portal');
    try {
      const portalUrl = await openBillingPortal();
      await Linking.openURL(portalUrl);
    } catch (err: any) {
      Alert.alert('Error', err.message ?? 'Could not open billing portal.');
    } finally {
      setLoading(null);
    }
  }

  const currentTier = user?.tier ?? 'free';

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.title}>Upgrade VetGPT</Text>
        <TouchableOpacity onPress={() => router.back()} style={styles.closeBtn} hitSlop={12}>
          <Text style={styles.closeText}>✕</Text>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={styles.subtitle}>
          Unlock AI image analysis, higher limits, and clinical decision support tools.
        </Text>

        {PLANS.map((plan) => {
          const isCurrent = currentTier === plan.key;
          const isPaid    = plan.key !== 'free';

          return (
            <View key={plan.key} style={[styles.card, plan.accent && styles.cardAccent]}>
              {plan.accent && (
                <View style={styles.popularBadge}>
                  <Text style={styles.popularText}>⭐ Most Popular</Text>
                </View>
              )}

              <View style={styles.planHeader}>
                <Text style={[styles.planName, { color: plan.color }]}>{plan.name}</Text>
                {isCurrent && (
                  <View style={styles.currentBadge}>
                    <Text style={styles.currentBadgeText}>Current</Text>
                  </View>
                )}
              </View>

              <View style={styles.priceRow}>
                <Text style={[styles.price, { color: plan.color }]}>{plan.price}</Text>
                <Text style={styles.period}>{plan.period}</Text>
              </View>

              {plan.features.map((f) => (
                <View key={f} style={styles.featureRow}>
                  <Text style={[styles.check, { color: plan.color }]}>✓</Text>
                  <Text style={styles.feature}>{f}</Text>
                </View>
              ))}

              {isPaid && !isCurrent && (
                <TouchableOpacity
                  style={[styles.ctaBtn, { backgroundColor: plan.color }]}
                  onPress={() => handleUpgrade(plan.key as 'premium' | 'clinic')}
                  disabled={loading !== null}
                  activeOpacity={0.85}
                >
                  {loading === plan.key
                    ? <ActivityIndicator color="#fff" />
                    : <Text style={styles.ctaText}>{plan.cta} →</Text>
                  }
                </TouchableOpacity>
              )}

              {isCurrent && isPaid && (
                <TouchableOpacity
                  style={styles.manageBtn}
                  onPress={handleManageSubscription}
                  disabled={loading === 'portal'}
                >
                  {loading === 'portal'
                    ? <ActivityIndicator size="small" color={Colors.textMuted} />
                    : <Text style={styles.manageBtnText}>Manage subscription →</Text>
                  }
                </TouchableOpacity>
              )}

              {isCurrent && !isPaid && (
                <View style={styles.currentPlanNote}>
                  <Text style={styles.currentPlanNoteText}>You are on the Free plan</Text>
                </View>
              )}
            </View>
          );
        })}

        <Text style={styles.legal}>
          Payments processed by Stripe. Cancel anytime. No refunds on partial months.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:    { flex: 1, backgroundColor: Colors.background },
  header:  {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    padding: Spacing.md, paddingTop: Spacing.lg,
    backgroundColor: Colors.surface,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
  },
  title:    { ...Typography.h3, color: Colors.textPrimary },
  closeBtn: { padding: 6 },
  closeText:{ fontSize: 20, color: Colors.textMuted },
  content:  { padding: Spacing.md, paddingBottom: Spacing.xxl },
  subtitle: { ...Typography.body, color: Colors.textSecondary, textAlign: 'center', marginBottom: Spacing.lg },

  card: {
    backgroundColor: Colors.surface, borderRadius: Radius.xl,
    padding: Spacing.lg, marginBottom: Spacing.md,
    borderWidth: 1, borderColor: Colors.border, ...Shadow.sm,
  },
  cardAccent: { borderWidth: 2, borderColor: Colors.accent },

  popularBadge: {
    backgroundColor: Colors.accent, borderRadius: Radius.full,
    paddingHorizontal: Spacing.md, paddingVertical: 4,
    alignSelf: 'flex-start', marginBottom: Spacing.sm,
  },
  popularText: { ...Typography.caption, color: '#fff', fontWeight: '700' },

  planHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
  planName:   { ...Typography.h3 },

  currentBadge: {
    backgroundColor: Colors.surfaceAlt, borderRadius: Radius.full,
    paddingHorizontal: 10, paddingVertical: 3,
  },
  currentBadgeText: { ...Typography.caption, color: Colors.textMuted, fontWeight: '600' },

  priceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 4, marginBottom: Spacing.md },
  price:    { ...Typography.h1 },
  period:   { ...Typography.body, color: Colors.textMuted },

  featureRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, marginBottom: 7 },
  check:      { fontWeight: '700', width: 16, marginTop: 1 },
  feature:    { ...Typography.body, color: Colors.textSecondary, flex: 1 },

  ctaBtn: {
    marginTop: Spacing.md, borderRadius: Radius.md, paddingVertical: 14,
    alignItems: 'center',
  },
  ctaText: { ...Typography.h4, color: '#fff' },

  manageBtn:     { marginTop: Spacing.md, alignItems: 'center', paddingVertical: 10 },
  manageBtnText: { ...Typography.label, color: Colors.primary },

  currentPlanNote:     { marginTop: Spacing.md, alignItems: 'center' },
  currentPlanNoteText: { ...Typography.caption, color: Colors.textMuted },

  legal: {
    ...Typography.caption, color: Colors.textMuted,
    textAlign: 'center', marginTop: Spacing.md, paddingHorizontal: Spacing.md,
  },
});

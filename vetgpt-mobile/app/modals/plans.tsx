import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { router } from 'expo-router';
import { Colors, Spacing, Typography } from '../../constants/theme';

export default function PlansModal() {
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Subscription Plans</Text>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.close}>✕</Text>
        </TouchableOpacity>
      </View>
      
      <View style={styles.planCard}>
        <Text style={styles.planName}>Free</Text>
        <Text style={styles.planPrice}>$0</Text>
        <Text style={styles.planFeatures}>• Basic RAG queries</Text>
        <Text style={styles.planFeatures}>• 20 queries/day</Text>
      </View>
      
      <View style={[styles.planCard, styles.premiumCard]}>
        <Text style={styles.planName}>Premium</Text>
        <Text style={styles.planPrice}>$9.99/mo</Text>
        <Text style={styles.planFeatures}>• Unlimited queries</Text>
        <Text style={styles.planFeatures}>• X-ray analysis</Text>
        <Text style={styles.planFeatures}>• Image recognition</Text>
        <Text style={styles.planFeatures}>• Advanced OCR</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background, padding: Spacing.lg },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.lg },
  title: { ...Typography.h2, color: Colors.textPrimary },
  close: { fontSize: 24, color: Colors.textMuted },
  planCard: { backgroundColor: Colors.surface, borderRadius: 12, padding: Spacing.lg, marginBottom: Spacing.md },
  premiumCard: { borderWidth: 2, borderColor: Colors.accent },
  planName: { ...Typography.h3, marginBottom: Spacing.sm },
  planPrice: { ...Typography.h1, color: Colors.primary, marginBottom: Spacing.md },
  planFeatures: { ...Typography.body, color: Colors.textSecondary, marginBottom: 4 },
});
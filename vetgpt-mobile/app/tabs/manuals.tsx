/**
 * vetgpt-mobile/app/(tabs)/manuals.tsx
 * Browse indexed veterinary manuals grouped by category.
 */

import {
  View, Text, SectionList, TouchableOpacity,
  StyleSheet, SafeAreaView,
} from 'react-native';
import { Colors, Spacing, Radius, Typography, Shadow } from '../constants/theme';
import { useAppStore } from '../store';

const MANUAL_SECTIONS = [
  {
    title: '✅ Available Now (Open Access)',
    data: [
      { key: 'wikivet',    label: 'WikiVet',          sub: 'CC BY-SA · Full encyclopedia', source: 'wikivet' },
      { key: 'pubmed',     label: 'PubMed Abstracts',  sub: 'Public Domain · Research', source: 'pubmed' },
      { key: 'fao',        label: 'FAO Manuals',        sub: 'Open Access · Livestock', source: 'fao' },
      { key: 'oie_woah',   label: 'OIE/WOAH Codes',    sub: 'Open Access · Disease standards', source: 'oie_woah' },
      { key: 'eclinpath',  label: 'eClinPath',          sub: 'Open Access · Clinical pathology', source: 'eclinpath' },
    ],
  },
  {
    title: '⏳ Pending License',
    data: [
      { key: 'merck_vet',          label: 'Merck Veterinary Manual',     sub: 'Core reference', source: null },
      { key: 'plumbs',             label: "Plumb's Drug Handbook",        sub: 'Drug dosages', source: null },
      { key: 'blackwells_5min',    label: "Blackwell's 5-Min Consult",    sub: 'Quick reference', source: null },
      { key: 'fossum_surgery',     label: 'Fossum Small Animal Surgery',  sub: 'Surgical procedures', source: null },
      { key: 'jubb_kennedy_palmer',label: 'Jubb, Kennedy & Palmer',       sub: 'Pathology', source: null },
      { key: 'thralls_radiology',  label: "Thrall's Radiology",           sub: 'Diagnostic imaging', source: null },
    ],
  },
  {
    title: '📄 Add Your Own PDFs',
    data: [
      { key: 'upload', label: 'Upload PDF', sub: 'Tap to add your own manuals', source: 'upload' },
    ],
  },
];

interface ManualItem {
  key: string;
  label: string;
  sub: string;
  source: string | null;
}

export default function ManualsScreen() {
  const { setFilterSource } = useAppStore();

  function handlePress(item: ManualItem) {
    if (item.source === 'upload') {
      // Phase 2: trigger document picker
      return;
    }
    if (item.source) {
      setFilterSource(item.source);
      // Navigate to search with filter pre-set
    }
  }

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.title}>Manuals</Text>
        <Text style={styles.subtitle}>Browse your indexed veterinary library</Text>
      </View>

      <SectionList
        sections={MANUAL_SECTIONS}
        keyExtractor={(item) => item.key}
        contentContainerStyle={styles.list}
        stickySectionHeadersEnabled={false}
        renderSectionHeader={({ section }) => (
          <Text style={styles.sectionHeader}>{section.title}</Text>
        )}
        renderItem={({ item }) => (
          <TouchableOpacity
            style={[styles.card, !item.source && styles.cardLocked]}
            onPress={() => handlePress(item)}
            activeOpacity={item.source ? 0.7 : 1}
          >
            <View style={styles.cardContent}>
              <Text style={styles.cardLabel}>{item.label}</Text>
              <Text style={styles.cardSub}>{item.sub}</Text>
            </View>
            {item.source && item.source !== 'upload' && (
              <View style={styles.badge}>
                <Text style={styles.badgeText}>Search →</Text>
              </View>
            )}
            {!item.source && (
              <View style={styles.badgeLocked}>
                <Text style={styles.badgeLockedText}>Soon</Text>
              </View>
            )}
            {item.source === 'upload' && (
              <Text style={styles.uploadIcon}>+</Text>
            )}
          </TouchableOpacity>
        )}
      />
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
  subtitle: { ...Typography.caption, color: 'rgba(255,255,255,0.75)', marginTop: 2 },
  list: { padding: Spacing.md },
  sectionHeader: {
    ...Typography.label,
    color: Colors.textSecondary,
    marginTop: Spacing.lg,
    marginBottom: Spacing.sm,
  },
  card: {
    backgroundColor: Colors.surface,
    borderRadius: Radius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    ...Shadow.sm,
  },
  cardLocked: { opacity: 0.6 },
  cardContent: { flex: 1 },
  cardLabel: { ...Typography.h4, color: Colors.textPrimary },
  cardSub: { ...Typography.caption, color: Colors.textMuted, marginTop: 2 },
  badge: {
    backgroundColor: Colors.primary + '18',
    borderRadius: Radius.full,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  badgeText: { ...Typography.caption, color: Colors.primary, fontWeight: '700' },
  badgeLocked: {
    backgroundColor: Colors.surfaceAlt,
    borderRadius: Radius.full,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  badgeLockedText: { ...Typography.caption, color: Colors.textMuted },
  uploadIcon: {
    fontSize: 24, color: Colors.primary, fontWeight: '700',
    width: 36, textAlign: 'center',
  },
});

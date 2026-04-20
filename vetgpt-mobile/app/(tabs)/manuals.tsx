/**
 * vetgpt-mobile/app/(tabs)/manuals.tsx
 * Browse indexed veterinary manuals grouped by category.
 */

import {
  View, Text, SectionList, TouchableOpacity,
  StyleSheet, SafeAreaView, Alert, ActivityIndicator,
} from 'react-native';
import { Colors, Spacing, Radius, Typography, Shadow } from '../constants/theme';
import { useAppStore } from '../store';
import { router } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';
import { useMemo, useState } from 'react';
import * as FileSystem from 'expo-file-system';
import { getStoredToken } from '../lib/api';
import { set } from 'date-fns';

interface ManualItem {
  key: string;
  label: string;
  sub: string;
  source: string | null;
  species?: string[];
}

const MANUAL_SECTIONS = [
  {
    title: 'Available Now (Open Access)',
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


export default function ManualsScreen() {
  const [search, setSearch] = useState('');
  const { setFilterSource } = useAppStore();
  const [uploading, setUploading] = useState(false);
  const [uploadFiles, setUploadedFiles] = useState<string[]>([]);

  // Filter by search text
  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    if (!q) return MANUAL_SECTIONS;
    return MANUAL_SECTIONS.map(section => ({
      ...section,
      data: section.data.filter(
        m => m.label.toLowerCase().includes(q) || m.sub.toLowerCase().includes(q)
      )
    })).filter(section => section.data.length > 0);
  }, [search]);

  const sections = useMemo(() => {
    const available = filtered.map(section => ({
      ...section,
      data: section.data.filter(m => m.source !== null)
    })).filter(section => section.data.length > 0);
    const pending = filtered.map(section => ({
      ...section,
      data: section.data.filter(m => m.source === null)
    })).filter(section => section.data.length > 0);
    return [
      ...(available.length ? [{ title: '✅ Available Now (Open Access)', data: available.flatMap(s => s.data) }] : []),
      ...(pending.length  ? [{ title: '⏳ Pending License',             data: pending.flatMap(s => s.data)  }] : []),
    ];
  }, [filtered]);

  function validatePDF(file:DocumentPicker.DocumentPickerAsset): boolean {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      Alert.alert('Invalid file', 'Please select a PDF document.');
      return false;
    }
    if (file.size && file.size > 100 * 1024 * 1024) { // 100MB limit
      Alert.alert('File too large', 'Please select a PDF smaller than 100MB.');
      return false;
    }

    const safeName = file.name.replace(/[^a-z0-9.\-_]/gi, '_');
    if (safeName !== file.name) {
      Alert.alert('Invalid filename', 'Filename contains unsupported characters');
      return false;
    }

    return true;
  }

 

  async function uploadPDF() {
    setUploading(true);
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: 'application/pdf',
        copyToCacheDirectory: true,
        multiple: false,
      });

      if (result.canceled) return;

      if (!validatePDF(result.assets[0])) return;  

      const token = await getStoredToken();
      if (!token) {
        Alert.alert('Authentication required', 'Please sign in to upload manuals.');
        setUploading(false);
        router.push('/(auth)/signin');
        return;
      }

      // Upload to backend and add to manuals list
      if (result.assets && result.assets[0]) {
        
      const formData = new FormData();
      formData.append('file', {
        uri: result.assets[0].uri,
        name: result.assets[0].name.replace(/[^a-z0-9.\-_]/gi, '_'),
        type: 'application/pdf',
      } as any);

      //Backend uploading endpoint
      const res = await fetch('https://localhost:8000/api/manuals/upload', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'multipart/form-data',
        },
        body: formData,
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Upload failed');
      }

      const data = await res.json();
      setUploadedFiles(prev => [...prev, result.assets[0].name]);
      Alert.alert('Success', `${result.assets[0].name}" uploaded successfully.`);

      // Show upload progress
      //Call ingest endpoint
        //alert(`Selected file: ${result.name}`);
      }
    } catch (error) {
      console.error('Upload failed:', error);
      Alert.alert('Upload Failed', error.message || 'Could not upload file. Please try again.');
    }finally {
      setUploading(false);
    }
  }
   function handlePress(item: ManualItem) {
    if (item.source === 'upload') {
      // Call function to handle pdf flow
      uploadPDF();
      return;
    }
    if (item.source) {
      setFilterSource(item.source);
      router.push({
        pathname: '/(tabs)/search',
        params: { q: '', source: item.source }
      });
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

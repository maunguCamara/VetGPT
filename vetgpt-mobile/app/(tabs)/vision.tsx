/**
 * vetgpt-mobile/app/(tabs)/vision.tsx
 *
 * Phase 3 — Premium Vision Screen.
 * Camera capture or gallery pick → choose analysis type → results.
 *
 * Features:
 * - Camera capture (live) or gallery upload
 * - DICOM file picker for X-rays
 * - Analysis type selector (wound, lesion, parasite, cytology, X-ray, OCR)
 * - Optional free-text question
 * - Results with RAG context, citations, disclaimer
 * - Premium gate for free users
 */

import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView,
  SafeAreaView, ActivityIndicator, TextInput, Alert,
  Image, Platform,
} from 'react-native';
import { useState } from 'react';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import { useAuthStore } from '../../store';
import {
  analyzeImage, analyzeXray, analyzeWound, analyzeLesion,
  analyzeParasite, analyzeCytology, extractOCRText,
  VisionAnalysisResult, OCRResult, ImageType,
} from '../lib/visionApi';
import { Colors, Spacing, Radius, Typography, Shadow } from '../../constants/theme';

// ─── Analysis type config ─────────────────────────────────────────────────────

interface AnalysisTypeConfig {
  id: ImageType | 'ocr';
  label: string;
  emoji: string;
  description: string;
  acceptsDicom: boolean;
}

const ANALYSIS_TYPES: AnalysisTypeConfig[] = [
  { id: 'wound',     label: 'Wound',      emoji: '🩹', description: 'Wound assessment and classification',    acceptsDicom: false },
  { id: 'lesion',    label: 'Skin lesion', emoji: '🔬', description: 'Dermatological lesion differentials',   acceptsDicom: false },
  { id: 'parasite',  label: 'Parasite',   emoji: '🦟', description: 'Parasite identification',               acceptsDicom: false },
  { id: 'cytology',  label: 'Cytology',   emoji: '🧫', description: 'Cytology / histology slide',            acceptsDicom: false },
  { id: 'xray',      label: 'X-ray',      emoji: '🩻', description: 'Radiograph analysis (JPEG or DICOM)',   acceptsDicom: true  },
  { id: 'ocr',       label: 'OCR',        emoji: '📄', description: 'Extract text from image',               acceptsDicom: false },
  { id: 'general',   label: 'General',    emoji: '🏥', description: 'General clinical image analysis',       acceptsDicom: false },
];

// ─── Premium gate ─────────────────────────────────────────────────────────────

function PremiumGate() {
  return (
    <View style={styles.gateContainer}>
      <Text style={styles.gateEmoji}>⭐</Text>
      <Text style={styles.gateTitle}>Premium Feature</Text>
      <Text style={styles.gateSub}>
        AI image analysis — wounds, lesions, parasites, cytology slides,
        and X-ray interpretation — requires a VetGPT Premium subscription.
      </Text>
      <View style={styles.featureList}>
        {[
          '🩹 Wound assessment & classification',
          '🔬 Dermatological lesion differentials',
          '🦟 Parasite identification',
          '🧫 Cytology slide interpretation',
          '🩻 X-ray & DICOM radiograph analysis',
          '📄 Clinical text extraction (OCR)',
        ].map((f) => (
          <Text key={f} style={styles.featureItem}>{f}</Text>
        ))}
      </View>
      <TouchableOpacity style={styles.upgradeBtn} activeOpacity={0.85}>
        <Text style={styles.upgradeBtnText}>Upgrade to Premium →</Text>
      </TouchableOpacity>
    </View>
  );
}

// ─── Result display ───────────────────────────────────────────────────────────

function AnalysisResult({ result }: { result: VisionAnalysisResult | OCRResult }) {
  const isOcr = 'word_count' in result;

  if (isOcr) {
    const ocr = result as OCRResult;
    return (
      <View style={styles.resultCard}>
        <View style={styles.resultHeader}>
          <Text style={styles.resultLabel}>📄 Extracted Text</Text>
          <Text style={styles.resultMeta}>{ocr.word_count} words</Text>
        </View>
        <Text style={styles.ocrText} selectable>{ocr.text || 'No text detected.'}</Text>
      </View>
    );
  }

  const vision = result as VisionAnalysisResult;
  return (
    <View>
      <View style={styles.resultCard}>
        <View style={styles.resultHeader}>
          <Text style={styles.resultLabel}>AI Analysis</Text>
          <Text style={styles.resultMeta}>
            {vision.engine_used.toUpperCase()} · {vision.latency_ms}ms
          </Text>
        </View>
        <Text style={styles.analysisText} selectable>{vision.analysis}</Text>
      </View>

      {vision.rag_context.length > 0 && (
        <View style={styles.ragCard}>
          <Text style={styles.ragLabel}>Supporting references</Text>
          {vision.rag_context.map((c, i) => (
            <View key={i} style={styles.ragItem}>
              <Text style={styles.ragTitle}>{c.document_title} — p.{c.page_number}</Text>
              <Text style={styles.ragExcerpt} numberOfLines={2}>{c.text}</Text>
            </View>
          ))}
        </View>
      )}

      <View style={styles.disclaimerCard}>
        <Text style={styles.disclaimerText}>{vision.disclaimer}</Text>
      </View>
    </View>
  );
}

// ─── Main Screen ──────────────────────────────────────────────────────────────

export default function VisionScreen() {
  const { user } = useAuthStore();
  const isPremium = user?.tier === 'premium' || user?.tier === 'clinic';

  const [selectedType, setSelectedType]   = useState<AnalysisTypeConfig>(ANALYSIS_TYPES[0]);
  const [imageUri, setImageUri]           = useState<string | null>(null);
  const [query, setQuery]                 = useState('');
  const [loading, setLoading]             = useState(false);
  const [result, setResult]               = useState<VisionAnalysisResult | OCRResult | null>(null);
  const [error, setError]                 = useState('');

  // ── Image selection ─────────────────────────────────────────────────────────

  async function pickFromCamera() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      Alert.alert('Camera permission required', 'Allow camera access in Settings.');
      return;
    }
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.9,
      allowsEditing: true,
    });
    if (!result.canceled && result.assets[0]) {
      setImageUri(result.assets[0].uri);
      setResult(null);
      setError('');
    }
  }

  async function pickFromGallery() {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert('Gallery permission required', 'Allow photo library access in Settings.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.9,
    });
    if (!result.canceled && result.assets[0]) {
      setImageUri(result.assets[0].uri);
      setResult(null);
      setError('');
    }
  }

  async function pickDicom() {
    const result = await DocumentPicker.getDocumentAsync({
      type: ['application/dicom', '*/*'],
      copyToCacheDirectory: true,
    });
    if (!result.canceled && result.assets[0]) {
      const uri = result.assets[0].uri;
      if (!uri.toLowerCase().endsWith('.dcm') &&
          !result.assets[0].mimeType?.includes('dicom')) {
        Alert.alert('Invalid file', 'Please select a DICOM (.dcm) file.');
        return;
      }
      setImageUri(uri);
      setResult(null);
      setError('');
    }
  }

  // ── Analysis ────────────────────────────────────────────────────────────────

  async function runAnalysis() {
    if (!imageUri) {
      Alert.alert('No image selected', 'Please capture or select an image first.');
      return;
    }
    setLoading(true);
    setError('');
    setResult(null);

    try {
      let analysisResult: VisionAnalysisResult | OCRResult;

      switch (selectedType.id) {
        case 'xray':      analysisResult = await analyzeXray(imageUri, query);     break;
        case 'wound':     analysisResult = await analyzeWound(imageUri, query);    break;
        case 'lesion':    analysisResult = await analyzeLesion(imageUri, query);   break;
        case 'parasite':  analysisResult = await analyzeParasite(imageUri, query); break;
        case 'cytology':  analysisResult = await analyzeCytology(imageUri, query); break;
        case 'ocr':       analysisResult = await extractOCRText(imageUri);         break;
        default:          analysisResult = await analyzeImage(imageUri, selectedType.id as ImageType, query); break;
      }

      setResult(analysisResult);
    } catch (err: any) {
      setError(err.message ?? 'Analysis failed. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setImageUri(null);
    setResult(null);
    setError('');
    setQuery('');
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  if (!isPremium) return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Vision Analysis</Text>
        <Text style={styles.headerSub}>Premium feature</Text>
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        <PremiumGate />
      </ScrollView>
    </SafeAreaView>
  );

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Vision Analysis</Text>
        <Text style={styles.headerSub}>AI-powered clinical image interpretation</Text>
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">

        {/* Analysis type selector */}
        <Text style={styles.sectionLabel}>Analysis type</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.typeScroll}>
          {ANALYSIS_TYPES.map((type) => (
            <TouchableOpacity
              key={type.id}
              style={[styles.typeChip, selectedType.id === type.id && styles.typeChipActive]}
              onPress={() => { setSelectedType(type); setResult(null); setImageUri(null); }}
              activeOpacity={0.75}
            >
              <Text style={styles.typeEmoji}>{type.emoji}</Text>
              <Text style={[styles.typeLabel, selectedType.id === type.id && styles.typeLabelActive]}>
                {type.label}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        <Text style={styles.typeDescription}>{selectedType.description}</Text>

        {/* Image selection */}
        <Text style={styles.sectionLabel}>Image</Text>
        {imageUri ? (
          <View style={styles.imagePreviewContainer}>
            <Image source={{ uri: imageUri }} style={styles.imagePreview} resizeMode="cover" />
            <TouchableOpacity style={styles.removeImageBtn} onPress={reset}>
              <Text style={styles.removeImageText}>✕ Remove</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.imagePicker}>
            <TouchableOpacity style={styles.imagePickBtn} onPress={pickFromCamera} activeOpacity={0.8}>
              <Text style={styles.imagePickEmoji}>📷</Text>
              <Text style={styles.imagePickLabel}>Camera</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.imagePickBtn} onPress={pickFromGallery} activeOpacity={0.8}>
              <Text style={styles.imagePickEmoji}>🖼️</Text>
              <Text style={styles.imagePickLabel}>Gallery</Text>
            </TouchableOpacity>
            {selectedType.acceptsDicom && (
              <TouchableOpacity style={styles.imagePickBtn} onPress={pickDicom} activeOpacity={0.8}>
                <Text style={styles.imagePickEmoji}>🩻</Text>
                <Text style={styles.imagePickLabel}>DICOM</Text>
              </TouchableOpacity>
            )}
          </View>
        )}

        {/* Optional question */}
        {selectedType.id !== 'ocr' && (
          <>
            <Text style={styles.sectionLabel}>Additional question (optional)</Text>
            <TextInput
              style={styles.queryInput}
              placeholder={`e.g. Is this infected? How old is this wound?`}
              placeholderTextColor={Colors.textMuted}
              value={query}
              onChangeText={setQuery}
              multiline
              maxLength={500}
            />
          </>
        )}

        {/* Analyse button */}
        <TouchableOpacity
          style={[styles.analyseBtn, (!imageUri || loading) && styles.analyseBtnDisabled]}
          onPress={runAnalysis}
          disabled={!imageUri || loading}
          activeOpacity={0.85}
        >
          {loading ? (
            <View style={styles.analyseBtnInner}>
              <ActivityIndicator color="#fff" />
              <Text style={styles.analyseBtnText}>Analysing...</Text>
            </View>
          ) : (
            <Text style={styles.analyseBtnText}>
              {selectedType.emoji} Run {selectedType.label} Analysis
            </Text>
          )}
        </TouchableOpacity>

        {/* Error */}
        {!!error && (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {/* Result */}
        {result && <AnalysisResult result={result} />}

      </ScrollView>
    </SafeAreaView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.md, paddingTop: Spacing.lg, paddingBottom: Spacing.md,
  },
  headerTitle: { ...Typography.h3, color: '#fff' },
  headerSub: { ...Typography.caption, color: 'rgba(255,255,255,0.75)', marginTop: 2 },
  content: { padding: Spacing.md, paddingBottom: Spacing.xxl },

  sectionLabel: {
    ...Typography.label, color: Colors.textMuted,
    marginBottom: Spacing.sm, marginTop: Spacing.md,
  },

  typeScroll: { marginBottom: 4 },
  typeChip: {
    alignItems: 'center', backgroundColor: Colors.surface,
    borderRadius: Radius.lg, borderWidth: 1, borderColor: Colors.border,
    padding: Spacing.sm, marginRight: Spacing.sm, minWidth: 72,
  },
  typeChipActive: { backgroundColor: Colors.primary, borderColor: Colors.primary },
  typeEmoji: { fontSize: 22, marginBottom: 4 },
  typeLabel: { ...Typography.caption, color: Colors.textSecondary, textAlign: 'center' },
  typeLabelActive: { color: '#fff', fontWeight: '600' },
  typeDescription: { ...Typography.bodySmall, color: Colors.textSecondary, marginBottom: Spacing.xs },

  imagePicker: {
    flexDirection: 'row', gap: Spacing.md,
    backgroundColor: Colors.surface, borderRadius: Radius.lg,
    borderWidth: 1, borderColor: Colors.border,
    borderStyle: 'dashed', padding: Spacing.xl,
    justifyContent: 'center',
  },
  imagePickBtn: { alignItems: 'center', gap: 6, flex: 1 },
  imagePickEmoji: { fontSize: 32 },
  imagePickLabel: { ...Typography.label, color: Colors.textSecondary },

  imagePreviewContainer: { borderRadius: Radius.lg, overflow: 'hidden', ...Shadow.sm },
  imagePreview: { width: '100%', height: 220 },
  removeImageBtn: {
    backgroundColor: Colors.error, padding: Spacing.sm, alignItems: 'center',
  },
  removeImageText: { ...Typography.label, color: '#fff' },

  queryInput: {
    borderWidth: 1, borderColor: Colors.border, borderRadius: Radius.md,
    paddingHorizontal: Spacing.md, paddingVertical: 10,
    ...Typography.body, color: Colors.textPrimary,
    backgroundColor: Colors.surface, minHeight: 80, textAlignVertical: 'top',
  },

  analyseBtn: {
    backgroundColor: Colors.primary, borderRadius: Radius.md,
    paddingVertical: 16, alignItems: 'center', marginTop: Spacing.md,
  },
  analyseBtnDisabled: { opacity: 0.5 },
  analyseBtnInner: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm },
  analyseBtnText: { ...Typography.h4, color: '#fff' },

  errorBox: {
    backgroundColor: '#FEE', borderRadius: Radius.md, padding: Spacing.md,
    borderWidth: 1, borderColor: Colors.error, marginTop: Spacing.md,
  },
  errorText: { ...Typography.body, color: Colors.error },

  resultCard: {
    backgroundColor: Colors.surface, borderRadius: Radius.lg,
    padding: Spacing.md, marginTop: Spacing.md,
    borderLeftWidth: 4, borderLeftColor: Colors.primary, ...Shadow.sm,
  },
  resultHeader: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', marginBottom: Spacing.sm,
  },
  resultLabel: { ...Typography.label, color: Colors.primary },
  resultMeta: { ...Typography.caption, color: Colors.textMuted },
  analysisText: { ...Typography.body, color: Colors.textPrimary, lineHeight: 22 },
  ocrText: {
    ...Typography.mono, color: Colors.textPrimary,
    backgroundColor: Colors.background, padding: Spacing.sm, borderRadius: Radius.sm,
  },

  ragCard: {
    backgroundColor: Colors.surfaceAlt, borderRadius: Radius.lg,
    padding: Spacing.md, marginTop: Spacing.sm,
  },
  ragLabel: { ...Typography.label, color: Colors.textMuted, marginBottom: Spacing.sm },
  ragItem: { marginBottom: Spacing.sm },
  ragTitle: { ...Typography.label, color: Colors.textPrimary },
  ragExcerpt: { ...Typography.caption, color: Colors.textSecondary, marginTop: 2 },

  disclaimerCard: {
    backgroundColor: Colors.premiumBg, borderRadius: Radius.md,
    padding: Spacing.md, marginTop: Spacing.sm,
    borderWidth: 1, borderColor: Colors.accent + '44',
  },
  disclaimerText: { ...Typography.caption, color: Colors.textSecondary, fontStyle: 'italic' },

  // Premium gate
  gateContainer: { alignItems: 'center', padding: Spacing.lg },
  gateEmoji: { fontSize: 56, marginBottom: Spacing.md },
  gateTitle: { ...Typography.h2, color: Colors.accent, marginBottom: Spacing.sm },
  gateSub: { ...Typography.body, color: Colors.textSecondary, textAlign: 'center', marginBottom: Spacing.lg },
  featureList: {
    alignSelf: 'stretch', backgroundColor: Colors.surface,
    borderRadius: Radius.lg, padding: Spacing.md, gap: 8, marginBottom: Spacing.lg,
    ...Shadow.sm,
  },
  featureItem: { ...Typography.body, color: Colors.textPrimary },
  upgradeBtn: {
    backgroundColor: Colors.accent, borderRadius: Radius.md,
    paddingVertical: 14, paddingHorizontal: Spacing.xl,
  },
  upgradeBtnText: { ...Typography.h4, color: '#fff' },
});

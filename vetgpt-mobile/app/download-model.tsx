/**
 * vetgpt-mobile/app/download-model.tsx
 *
 * Full-screen model download UI.
 * Shows: storage check, WiFi warning, progress bar,
 *        pause/resume, cancel, and success state.
 */

import {
  View, Text, TouchableOpacity, StyleSheet,
  SafeAreaView, Alert, ScrollView,
} from 'react-native';
import { useState, useEffect } from 'react';
import { router } from 'expo-router';
import { modelManager, ModelState, getRecommendedModel } from '../lib/modelManager';
import { offlineRouter } from '../lib/offlineRouter';
import { useAppStore } from '../store';
import { Colors, Spacing, Radius, Typography, Shadow } from '../constants/theme';

function formatBytes(bytes: number): string {
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

function ProgressBar({ pct }: { pct: number }) {
  return (
    <View style={styles.progressTrack}>
      <View style={[styles.progressFill, { width: `${Math.min(pct, 100)}%` }]} />
    </View>
  );
}

function RequirementRow({
  label, met, detail,
}: { label: string; met: boolean; detail: string }) {
  return (
    <View style={styles.reqRow}>
      <Text style={[styles.reqIcon, { color: met ? Colors.success : Colors.error }]}>
        {met ? '✓' : '✗'}
      </Text>
      <View>
        <Text style={styles.reqLabel}>{label}</Text>
        <Text style={styles.reqDetail}>{detail}</Text>
      </View>
    </View>
  );
}

export default function DownloadModelScreen() {
  const [modelState, setModelState] = useState<ModelState>({
    status: 'not_downloaded',
    progressBytes: 0,
    totalBytes: 0,
    progressPct: 0,
    engine: null,
  });
  const [freeStorageGB, setFreeStorageGB] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const { setHasLocalModel } = useAppStore();
  const spec = getRecommendedModel();

  useEffect(() => {
    loadInitialState();
  }, []);

  async function loadInitialState() {
    const state = await modelManager.getModelState();
    setModelState(state);
    const freeGB = await modelManager.getFreeDiskSpaceGB();
    setFreeStorageGB(freeGB);

    if (state.status === 'ready') {
      setHasLocalModel(true);
    }
  }

  async function startDownload() {
    const hasSufficientStorage = await modelManager.hasSufficientStorage();
    if (!hasSufficientStorage) {
      Alert.alert(
        'Not enough storage',
        `You need at least ${(spec.sizeBytes / 1024 ** 3 * 1.1).toFixed(1)} GB free. ` +
        `You have ${freeStorageGB.toFixed(1)} GB available.`
      );
      return;
    }

    setIsPaused(false);
    await modelManager.download((state) => {
      setModelState({ ...state });
      if (state.status === 'ready') {
        setHasLocalModel(true);
        offlineRouter.init();  // initialise engine immediately
      }
    });
  }

  async function pauseDownload() {
    await modelManager.pauseDownload();
    setIsPaused(true);
  }

  async function resumeDownload() {
    setIsPaused(false);
    await modelManager.resumeDownload((state) => {
      setModelState({ ...state });
      if (state.status === 'ready') {
        setHasLocalModel(true);
        offlineRouter.init();
      }
    });
  }

  async function cancelDownload() {
    Alert.alert('Cancel download?', 'Progress will be lost.', [
      { text: 'Keep downloading', style: 'cancel' },
      {
        text: 'Cancel',
        style: 'destructive',
        onPress: async () => {
          await modelManager.pauseDownload();
          setModelState({
            status: 'not_downloaded',
            progressBytes: 0,
            totalBytes: spec.sizeBytes,
            progressPct: 0,
            engine: null,
          });
          setIsPaused(false);
        },
      },
    ]);
  }

  async function deleteModel() {
    Alert.alert('Delete offline model?', 'You can re-download it anytime.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          await modelManager.deleteModel();
          setHasLocalModel(false);
          setModelState({
            status: 'not_downloaded',
            progressBytes: 0,
            totalBytes: spec.sizeBytes,
            progressPct: 0,
            engine: null,
          });
        },
      },
    ]);
  }

  const isDownloading = modelState.status === 'downloading';
  const isReady       = modelState.status === 'ready';
  const isVerifying   = modelState.status === 'verifying';
  const isError       = modelState.status === 'error';
  const storageMet    = freeStorageGB >= spec.sizeMB / 1024 * 1.1;

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.content}>

        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.back}>
            <Text style={styles.backText}>← Back</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Offline Model</Text>
          <Text style={styles.subtitle}>Use VetGPT without internet</Text>
        </View>

        {/* Model card */}
        <View style={styles.modelCard}>
          <View style={styles.modelIcon}>
            <Text style={styles.modelEmoji}>🧠</Text>
          </View>
          <View style={styles.modelInfo}>
            <Text style={styles.modelName}>{spec.name}</Text>
            <Text style={styles.modelMeta}>
              {spec.sizeMB} MB · Requires {spec.minRamGB} GB RAM
            </Text>
            <Text style={styles.modelDesc}>{spec.description}</Text>
          </View>
        </View>

        {/* Requirements */}
        {!isReady && (
          <View style={styles.requirements}>
            <Text style={styles.sectionLabel}>Requirements</Text>
            <RequirementRow
              label="Storage"
              met={storageMet}
              detail={`${freeStorageGB.toFixed(1)} GB free · Need ${(spec.sizeMB / 1024 * 1.1).toFixed(1)} GB`}
            />
            <RequirementRow
              label="RAM"
              met={true}
              detail={`${spec.minRamGB} GB minimum — modern phones meet this`}
            />
            <RequirementRow
              label="WiFi required"
              met={true}
              detail="Download will pause on mobile data"
            />
          </View>
        )}

        {/* Progress */}
        {(isDownloading || isVerifying) && (
          <View style={styles.progressSection}>
            <View style={styles.progressHeader}>
              <Text style={styles.progressLabel}>
                {isVerifying ? 'Verifying...' : `Downloading — ${modelState.progressPct}%`}
              </Text>
              <Text style={styles.progressBytes}>
                {formatBytes(modelState.progressBytes)} / {formatBytes(modelState.totalBytes)}
              </Text>
            </View>
            <ProgressBar pct={modelState.progressPct} />

            <View style={styles.downloadActions}>
              {!isPaused && isDownloading && (
                <TouchableOpacity style={styles.secondaryBtn} onPress={pauseDownload}>
                  <Text style={styles.secondaryBtnText}>Pause</Text>
                </TouchableOpacity>
              )}
              {isPaused && (
                <TouchableOpacity style={styles.primaryBtn} onPress={resumeDownload}>
                  <Text style={styles.primaryBtnText}>Resume</Text>
                </TouchableOpacity>
              )}
              <TouchableOpacity style={styles.dangerBtn} onPress={cancelDownload}>
                <Text style={styles.dangerBtnText}>Cancel</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Error */}
        {isError && (
          <View style={styles.errorBox}>
            <Text style={styles.errorTitle}>Download failed</Text>
            <Text style={styles.errorMsg}>{modelState.error}</Text>
            <TouchableOpacity style={styles.primaryBtn} onPress={startDownload}>
              <Text style={styles.primaryBtnText}>Try again</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Ready state */}
        {isReady && (
          <View style={styles.readyBox}>
            <Text style={styles.readyIcon}>✅</Text>
            <Text style={styles.readyTitle}>Offline model ready</Text>
            <Text style={styles.readySub}>
              VetGPT will automatically use the on-device model
              when you're offline. Engine: {modelState.engine === 'mlc' ? 'MLC (Metal GPU)' : 'llama.cpp'}.
            </Text>
            <TouchableOpacity style={styles.dangerBtn} onPress={deleteModel}>
              <Text style={styles.dangerBtnText}>Delete model ({spec.sizeMB} MB)</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Download button */}
        {modelState.status === 'not_downloaded' && (
          <View style={styles.downloadSection}>
            <Text style={styles.downloadNote}>
              Download once over WiFi. Works completely offline after that.
              You can delete it anytime to free up space.
            </Text>
            <TouchableOpacity
              style={[styles.downloadBtn, !storageMet && styles.downloadBtnDisabled]}
              onPress={startDownload}
              disabled={!storageMet}
              activeOpacity={0.85}
            >
              <Text style={styles.downloadBtnText}>
                Download {spec.sizeMB} MB
              </Text>
            </TouchableOpacity>
            {!storageMet && (
              <Text style={styles.storageWarning}>
                Free up storage before downloading.
              </Text>
            )}
          </View>
        )}

        {/* Engine info */}
        <View style={styles.infoBox}>
          <Text style={styles.infoTitle}>About the engines</Text>
          <Text style={styles.infoText}>
            <Text style={{ fontWeight: '700' }}>llama.cpp</Text> — runs on Android and iOS.
            Uses CPU with optional GPU acceleration. Proven, stable, widely used.{'\n\n'}
            <Text style={{ fontWeight: '700' }}>MLC LLM</Text> — iOS only. Compiles the
            model to use iPhone's Metal GPU directly. Up to 3× faster than llama.cpp on
            supported devices (iPhone 12+).
          </Text>
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.background },
  content: { padding: Spacing.md, paddingBottom: Spacing.xxl },

  header: {
    backgroundColor: Colors.primary,
    margin: -Spacing.md,
    marginBottom: Spacing.md,
    padding: Spacing.md,
    paddingTop: Spacing.lg,
  },
  back: { marginBottom: Spacing.sm },
  backText: { color: 'rgba(255,255,255,0.8)', ...Typography.body },
  title: { ...Typography.h2, color: '#fff' },
  subtitle: { ...Typography.body, color: 'rgba(255,255,255,0.75)', marginTop: 4 },

  modelCard: {
    flexDirection: 'row',
    backgroundColor: Colors.surface,
    borderRadius: Radius.lg,
    padding: Spacing.md,
    gap: Spacing.md,
    marginBottom: Spacing.md,
    ...Shadow.sm,
  },
  modelIcon: {
    width: 52, height: 52, borderRadius: Radius.md,
    backgroundColor: Colors.primary + '18',
    alignItems: 'center', justifyContent: 'center',
  },
  modelEmoji: { fontSize: 28 },
  modelInfo: { flex: 1 },
  modelName: { ...Typography.h4, color: Colors.textPrimary },
  modelMeta: { ...Typography.caption, color: Colors.textMuted, marginTop: 2 },
  modelDesc: { ...Typography.bodySmall, color: Colors.textSecondary, marginTop: 4 },

  sectionLabel: {
    ...Typography.label, color: Colors.textMuted,
    marginBottom: Spacing.sm,
  },
  requirements: { marginBottom: Spacing.md },
  reqRow: {
    flexDirection: 'row',
    gap: Spacing.sm,
    backgroundColor: Colors.surface,
    borderRadius: Radius.md,
    padding: Spacing.md,
    marginBottom: Spacing.sm,
    alignItems: 'flex-start',
    ...Shadow.sm,
  },
  reqIcon: { fontSize: 18, width: 22 },
  reqLabel: { ...Typography.h4, color: Colors.textPrimary },
  reqDetail: { ...Typography.caption, color: Colors.textSecondary, marginTop: 2 },

  progressSection: {
    backgroundColor: Colors.surface,
    borderRadius: Radius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.md,
    ...Shadow.sm,
  },
  progressHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: Spacing.sm,
  },
  progressLabel: { ...Typography.h4, color: Colors.textPrimary },
  progressBytes: { ...Typography.caption, color: Colors.textMuted },
  progressTrack: {
    height: 10, backgroundColor: Colors.surfaceAlt,
    borderRadius: Radius.full, overflow: 'hidden',
  },
  progressFill: {
    height: '100%', backgroundColor: Colors.primary,
    borderRadius: Radius.full,
  },
  downloadActions: {
    flexDirection: 'row', gap: Spacing.sm, marginTop: Spacing.md,
  },

  downloadSection: { marginBottom: Spacing.md },
  downloadNote: {
    ...Typography.bodySmall, color: Colors.textSecondary,
    marginBottom: Spacing.md,
  },
  downloadBtn: {
    backgroundColor: Colors.primary, borderRadius: Radius.md,
    paddingVertical: 16, alignItems: 'center',
  },
  downloadBtnDisabled: { opacity: 0.5 },
  downloadBtnText: { ...Typography.h4, color: '#fff' },
  storageWarning: { ...Typography.caption, color: Colors.error, marginTop: Spacing.sm },

  primaryBtn: {
    flex: 1, backgroundColor: Colors.primary,
    borderRadius: Radius.md, paddingVertical: 12, alignItems: 'center',
  },
  primaryBtnText: { ...Typography.label, color: '#fff' },
  secondaryBtn: {
    flex: 1, borderWidth: 1, borderColor: Colors.border,
    borderRadius: Radius.md, paddingVertical: 12, alignItems: 'center',
  },
  secondaryBtnText: { ...Typography.label, color: Colors.textSecondary },
  dangerBtn: {
    flex: 1, borderWidth: 1, borderColor: Colors.error,
    borderRadius: Radius.md, paddingVertical: 12, alignItems: 'center',
    marginTop: Spacing.md,
  },
  dangerBtnText: { ...Typography.label, color: Colors.error },

  readyBox: {
    backgroundColor: Colors.surface, borderRadius: Radius.lg,
    padding: Spacing.lg, alignItems: 'center', marginBottom: Spacing.md,
    borderWidth: 1, borderColor: Colors.success + '44',
    ...Shadow.sm,
  },
  readyIcon: { fontSize: 40, marginBottom: Spacing.sm },
  readyTitle: { ...Typography.h3, color: Colors.success },
  readySub: {
    ...Typography.bodySmall, color: Colors.textSecondary,
    textAlign: 'center', marginTop: Spacing.sm,
  },

  errorBox: {
    backgroundColor: '#FEE', borderRadius: Radius.lg,
    padding: Spacing.md, marginBottom: Spacing.md,
    borderWidth: 1, borderColor: Colors.error,
    ...Shadow.sm,
  },
  errorTitle: { ...Typography.h4, color: Colors.error },
  errorMsg: { ...Typography.bodySmall, color: Colors.error, marginVertical: Spacing.sm },

  infoBox: {
    backgroundColor: Colors.surfaceAlt, borderRadius: Radius.lg,
    padding: Spacing.md, marginTop: Spacing.md,
  },
  infoTitle: { ...Typography.label, color: Colors.textSecondary, marginBottom: Spacing.sm },
  infoText: { ...Typography.bodySmall, color: Colors.textSecondary, lineHeight: 20 },
});

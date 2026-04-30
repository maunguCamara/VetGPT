/**
 * vetgpt-mobile/lib/modelManager.ts
 *
 * Manages the on-device Qwen2.5-3B model lifecycle.
 * NO expo-network — uses fetch-based connectivity + @react-native-community/netinfo.
 */

import * as FileSystem from 'expo-file-system';
import { Platform } from 'react-native';

// ─── Model specs ──────────────────────────────────────────────────────────────

export interface ModelSpec {
  id: string;
  name: string;
  engine: 'llamacpp' | 'mlc';
  platform: 'android' | 'ios' | 'both';
  url: string;
  filename: string;
  sizeBytes: number;
  sizeMB: number;
  minRamGB: number;
  description: string;
}

export const QWEN_GGUF: ModelSpec = {
  id:          'qwen2.5-3b-gguf',
  name:        'Qwen2.5-3B (llama.cpp)',
  engine:      'llamacpp',
  platform:    'both',
  url:         'https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf',
  filename:    'qwen2.5-3b-q4_k_m.gguf',
  sizeBytes:   1_930_000_000,
  sizeMB:      1930,
  minRamGB:    4,
  description: 'Quantized GGUF model for llama.cpp. Works on Android and iOS.',
};

export const QWEN_MLC: ModelSpec = {
  id:          'qwen2.5-3b-mlc',
  name:        'Qwen2.5-3B (MLC — iOS Metal)',
  engine:      'mlc',
  platform:    'ios',
  url:         'https://huggingface.co/mlc-ai/Qwen2.5-3B-Instruct-q4f16_1-MLC/resolve/main/',
  filename:    'qwen2.5-3b-mlc',
  sizeBytes:   2_100_000_000,
  sizeMB:      2100,
  minRamGB:    4,
  description: 'MLC-compiled model for iPhone Metal GPU. Faster than GGUF on iOS.',
};

export function getRecommendedModel(): ModelSpec {
  return Platform.OS === 'ios' ? QWEN_MLC : QWEN_GGUF;
}

// ─── Types ────────────────────────────────────────────────────────────────────

export type DownloadStatus =
  | 'not_downloaded'
  | 'downloading'
  | 'verifying'
  | 'ready'
  | 'error';

export interface ModelState {
  status:        DownloadStatus;
  progressBytes: number;
  totalBytes:    number;
  progressPct:   number;
  error?:        string;
  localPath?:    string;
  engine:        'llamacpp' | 'mlc' | null;
}

// ─── Network helpers — NO expo-network ───────────────────────────────────────

async function checkOnline(): Promise<boolean> {
  try {
    const ctrl    = new AbortController();
    const timeout = setTimeout(() => ctrl.abort(), 4000);
    const res     = await fetch(
      'https://dns.google/resolve?name=huggingface.co&type=A',
      { signal: ctrl.signal, method: 'HEAD' },
    );
    clearTimeout(timeout);
    return res.status < 500;
  } catch {
    return false;
  }
}

async function getConnectionType(): Promise<'wifi' | 'cellular' | 'unknown'> {
  try {
    // @react-native-community/netinfo ships with Expo SDK 51 — no prebuild needed
    const NetInfo = (await import('@react-native-community/netinfo')).default;
    const state   = await NetInfo.fetch();
    if (state.type === 'wifi')     return 'wifi';
    if (state.type === 'cellular') return 'cellular';
    return 'unknown';
  } catch {
    return 'unknown';   // Expo Go web — allow download
  }
}

// ─── Storage ──────────────────────────────────────────────────────────────────

const MODEL_DIR = `${FileSystem.documentDirectory}models/`;

// ─── Model Manager ────────────────────────────────────────────────────────────

export class ModelManager {
  private _resumable: FileSystem.DownloadResumable | null = null;

  async getModelState(): Promise<ModelState> {
    const spec      = getRecommendedModel();
    const localPath = `${MODEL_DIR}${spec.filename}`;
    try {
      const info = await FileSystem.getInfoAsync(localPath);
      if (info.exists) {
        return {
          status: 'ready', progressBytes: spec.sizeBytes,
          totalBytes: spec.sizeBytes, progressPct: 100,
          localPath, engine: spec.engine,
        };
      }
    } catch {}
    return {
      status: 'not_downloaded', progressBytes: 0,
      totalBytes: spec.sizeBytes, progressPct: 0, engine: null,
    };
  }

  async download(onProgress: (s: ModelState) => void): Promise<void> {
    const spec = getRecommendedModel();

    // Online check
    if (!(await checkOnline())) {
      return onProgress({
        status: 'error', progressBytes: 0, totalBytes: spec.sizeBytes,
        progressPct: 0, engine: null,
        error: 'No internet connection. Connect to WiFi to download.',
      });
    }

    // WiFi check — warn on cellular but don't block
    const conn = await getConnectionType();
    if (conn === 'cellular') {
      return onProgress({
        status: 'error', progressBytes: 0, totalBytes: spec.sizeBytes,
        progressPct: 0, engine: null,
        error: `Model is ${spec.sizeMB} MB. Connect to WiFi to avoid mobile data charges.`,
      });
    }

    // Storage check
    if (!(await this.hasSufficientStorage())) {
      const free = await this.getFreeDiskSpaceGB();
      return onProgress({
        status: 'error', progressBytes: 0, totalBytes: spec.sizeBytes,
        progressPct: 0, engine: null,
        error: `Insufficient storage. Need ~${(spec.sizeBytes / 1e9).toFixed(1)} GB, have ${free.toFixed(1)} GB free.`,
      });
    }

    await FileSystem.makeDirectoryAsync(MODEL_DIR, { intermediates: true });

    const localPath   = `${MODEL_DIR}${spec.filename}`;
    const partialPath = `${localPath}.part`;

    onProgress({
      status: 'downloading', progressBytes: 0,
      totalBytes: spec.sizeBytes, progressPct: 0, engine: null,
    });

    this._resumable = FileSystem.createDownloadResumable(
      spec.url, partialPath, {},
      ({ totalBytesWritten, totalBytesExpectedToWrite }) => {
        const total = totalBytesExpectedToWrite || spec.sizeBytes;
        onProgress({
          status: 'downloading',
          progressBytes: totalBytesWritten,
          totalBytes:    total,
          progressPct:   Math.round((totalBytesWritten / total) * 100),
          engine: null,
        });
      },
    );

    try {
      const result = await this._resumable.downloadAsync();
      if (!result?.uri) throw new Error('Download returned no URI.');

      await FileSystem.moveAsync({ from: partialPath, to: localPath });

      onProgress({
        status: 'verifying', progressBytes: spec.sizeBytes,
        totalBytes: spec.sizeBytes, progressPct: 99, engine: null,
      });

      const info = await FileSystem.getInfoAsync(localPath);
      if (!info.exists) throw new Error('File missing after download.');

      onProgress({
        status: 'ready', progressBytes: spec.sizeBytes,
        totalBytes: spec.sizeBytes, progressPct: 100,
        localPath, engine: spec.engine,
      });

    } catch (err: any) {
      await FileSystem.deleteAsync(partialPath, { idempotent: true });
      onProgress({
        status: 'error', progressBytes: 0,
        totalBytes: spec.sizeBytes, progressPct: 0, engine: null,
        error: err.message ?? 'Download failed. Try again.',
      });
    }
  }

  async pauseDownload():  Promise<void> { await this._resumable?.pauseAsync();  }
  async resumeDownload(): Promise<void> { await this._resumable?.resumeAsync(); }

  async deleteModel(): Promise<void> {
    const spec = getRecommendedModel();
    await FileSystem.deleteAsync(`${MODEL_DIR}${spec.filename}`, { idempotent: true });
  }

  async getFreeDiskSpaceGB(): Promise<number> {
    try { return (await FileSystem.getFreeDiskStorageAsync()) / (1024 ** 3); }
    catch { return 0; }
  }

  async hasSufficientStorage(): Promise<boolean> {
    const spec = getRecommendedModel();
    return (await this.getFreeDiskSpaceGB()) >= (spec.sizeBytes / (1024 ** 3)) * 1.1;
  }
}

export const modelManager = new ModelManager();
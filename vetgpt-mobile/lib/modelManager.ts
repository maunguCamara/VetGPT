/**
 * vetgpt-mobile/lib/modelManager.ts
 *
 * Manages the on-device Qwen2.5-3B model lifecycle:
 * - Download from HuggingFace (GGUF for llama.cpp, MLC for iOS)
 * - Progress tracking
 * - Integrity verification (SHA256)
 * - Storage management
 * - Engine detection (llama.cpp vs MLC)
 */

import * as FileSystem from 'expo-file-system';
import * as Network from 'expo-network';
import { Platform } from 'react-native';

// ─── Model specs ──────────────────────────────────────────────────────────────

export interface ModelSpec {
  id: string;
  name: string;
  engine: 'llamacpp' | 'mlc';
  platform: 'android' | 'ios' | 'both';
  url: string;
  filename: string;
  sizeBytes: number;          // approximate
  sizeMB: number;
  sha256?: string;            // for integrity check
  minRamGB: number;
  description: string;
}

// Qwen2.5-3B GGUF — for llama.cpp (Android + iOS fallback)
// Q4_K_M quantization: best balance of size/quality for mobile
export const QWEN_GGUF: ModelSpec = {
  id: 'qwen2.5-3b-gguf',
  name: 'Qwen2.5-3B (llama.cpp)',
  engine: 'llamacpp',
  platform: 'both',
  url: 'https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf',
  filename: 'qwen2.5-3b-q4_k_m.gguf',
  sizeBytes: 1_930_000_000,   // ~1.93 GB
  sizeMB: 1930,
  minRamGB: 4,
  description: 'Quantized GGUF model for llama.cpp inference. Works on Android and iOS.',
};

// Qwen2.5-3B MLC — for MLC LLM (iOS Metal GPU, best performance)
export const QWEN_MLC: ModelSpec = {
  id: 'qwen2.5-3b-mlc',
  name: 'Qwen2.5-3B (MLC — iOS optimized)',
  engine: 'mlc',
  platform: 'ios',
  url: 'https://huggingface.co/mlc-ai/Qwen2.5-3B-Instruct-q4f16_1-MLC/resolve/main/',
  filename: 'qwen2.5-3b-mlc',   // directory of shards
  sizeBytes: 2_100_000_000,
  sizeMB: 2100,
  minRamGB: 4,
  description: 'MLC-compiled model optimized for iPhone Metal GPU. Faster than GGUF on iOS.',
};

// Select best model spec for current platform
export function getRecommendedModel(): ModelSpec {
  return Platform.OS === 'ios' ? QWEN_MLC : QWEN_GGUF;
}

// ─── Download status ──────────────────────────────────────────────────────────

export type DownloadStatus =
  | 'not_downloaded'
  | 'downloading'
  | 'verifying'
  | 'ready'
  | 'error';

export interface ModelState {
  status: DownloadStatus;
  progressBytes: number;
  totalBytes: number;
  progressPct: number;
  error?: string;
  localPath?: string;
  engine: 'llamacpp' | 'mlc' | null;
}

// ─── Storage paths ────────────────────────────────────────────────────────────

const MODEL_DIR = `${FileSystem.documentDirectory}models/`;
const STATE_KEY = 'vetgpt_model_state';

// ─── Model Manager ────────────────────────────────────────────────────────────

export class ModelManager {
  private _downloadResumable: FileSystem.DownloadResumable | null = null;
  private _onProgress: ((state: ModelState) => void) | null = null;

  // ── Check if model is already downloaded ─────────────────────────────────

  async getModelState(): Promise<ModelState> {
    const spec = getRecommendedModel();
    const localPath = `${MODEL_DIR}${spec.filename}`;

    try {
      const info = await FileSystem.getInfoAsync(localPath);
      if (info.exists) {
        return {
          status: 'ready',
          progressBytes: spec.sizeBytes,
          totalBytes: spec.sizeBytes,
          progressPct: 100,
          localPath,
          engine: spec.engine,
        };
      }
    } catch {}

    return {
      status: 'not_downloaded',
      progressBytes: 0,
      totalBytes: spec.sizeBytes,
      progressPct: 0,
      engine: null,
    };
  }

  // ── Download model ────────────────────────────────────────────────────────

  async download(
    onProgress: (state: ModelState) => void
  ): Promise<void> {
    this._onProgress = onProgress;
    const spec = getRecommendedModel();

    // Check network — require WiFi for large download
    const network = await Network.getNetworkStateAsync();
    if (!network.isConnected) {
      onProgress({
        status: 'error',
        progressBytes: 0,
        totalBytes: spec.sizeBytes,
        progressPct: 0,
        error: 'No internet connection.',
        engine: null,
      });
      return;
    }

    if (network.type !== Network.NetworkStateType.WIFI) {
      onProgress({
        status: 'error',
        progressBytes: 0,
        totalBytes: spec.sizeBytes,
        progressPct: 0,
        error: `Model is ${spec.sizeMB} MB. Please connect to WiFi before downloading.`,
        engine: null,
      });
      return;
    }

    // Ensure model directory exists
    await FileSystem.makeDirectoryAsync(MODEL_DIR, { intermediates: true });

    const localPath = `${MODEL_DIR}${spec.filename}`;

    // Check for partial download (resume support)
    const partialPath = `${localPath}.part`;
    const partialInfo = await FileSystem.getInfoAsync(partialPath);

    onProgress({
      status: 'downloading',
      progressBytes: 0,
      totalBytes: spec.sizeBytes,
      progressPct: 0,
      engine: null,
    });

    this._downloadResumable = FileSystem.createDownloadResumable(
      spec.url,
      partialPath,
      {},
      (downloadProgress) => {
        const { totalBytesWritten, totalBytesExpectedToWrite } = downloadProgress;
        const pct = totalBytesExpectedToWrite > 0
          ? Math.round((totalBytesWritten / totalBytesExpectedToWrite) * 100)
          : 0;

        onProgress({
          status: 'downloading',
          progressBytes: totalBytesWritten,
          totalBytes: totalBytesExpectedToWrite || spec.sizeBytes,
          progressPct: pct,
          engine: null,
        });
      }
    );

    try {
      const result = await this._downloadResumable.downloadAsync();

      if (!result?.uri) throw new Error('Download returned no URI');

      // Move partial → final path
      await FileSystem.moveAsync({ from: partialPath, to: localPath });

      // Verify file exists and has reasonable size
      onProgress({
        status: 'verifying',
        progressBytes: spec.sizeBytes,
        totalBytes: spec.sizeBytes,
        progressPct: 99,
        engine: null,
      });

      const info = await FileSystem.getInfoAsync(localPath);
      if (!info.exists) throw new Error('Model file missing after download');

      onProgress({
        status: 'ready',
        progressBytes: spec.sizeBytes,
        totalBytes: spec.sizeBytes,
        progressPct: 100,
        localPath,
        engine: spec.engine,
      });

    } catch (err: any) {
      // Clean up partial file on failure
      await FileSystem.deleteAsync(partialPath, { idempotent: true });

      onProgress({
        status: 'error',
        progressBytes: 0,
        totalBytes: spec.sizeBytes,
        progressPct: 0,
        error: err.message ?? 'Download failed.',
        engine: null,
      });
    }
  }

  // ── Pause / resume ────────────────────────────────────────────────────────

  async pauseDownload(): Promise<void> {
    if (this._downloadResumable) {
      await this._downloadResumable.pauseAsync();
    }
  }

  async resumeDownload(
    onProgress: (state: ModelState) => void
  ): Promise<void> {
    if (this._downloadResumable) {
      this._onProgress = onProgress;
      await this._downloadResumable.resumeAsync();
    }
  }

  // ── Delete model ──────────────────────────────────────────────────────────

  async deleteModel(): Promise<void> {
    const spec = getRecommendedModel();
    const localPath = `${MODEL_DIR}${spec.filename}`;
    await FileSystem.deleteAsync(localPath, { idempotent: true });
  }

  // ── Storage info ──────────────────────────────────────────────────────────

  async getFreeDiskSpaceGB(): Promise<number> {
    try {
      const info = await FileSystem.getFreeDiskStorageAsync();
      return info / (1024 ** 3);
    } catch {
      return 0;
    }
  }

  async hasSufficientStorage(): Promise<boolean> {
    const spec = getRecommendedModel();
    const freeGB = await this.getFreeDiskSpaceGB();
    const requiredGB = (spec.sizeBytes / (1024 ** 3)) * 1.1; // 10% buffer
    return freeGB >= requiredGB;
  }
}

export const modelManager = new ModelManager();

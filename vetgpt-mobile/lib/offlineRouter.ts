/**
 * vetgpt-mobile/lib/offlineRouter.ts
 *
 * The routing brain — every query comes here first.
 *
 * Decision tree:
 *
 *   Online + model not loaded  →  Cloud API (FastAPI backend)
 *   Online + model loaded      →  Cloud API (cloud is better quality)
 *   Offline + model ready      →  Local inference (llama.cpp or MLC)
 *   Offline + no model         →  Error with helpful message
 *
 * The router also handles:
 *   - Local vector search before sending to on-device LLM
 *     (Phase 2: sqlite-vec bundled index for offline RAG)
 *   - Graceful fallback: if local inference fails → try cloud if online
 *   - Engine selection: MLC on iOS, llama.cpp on Android
 */

import { Platform } from 'react-native';
import { isOnline, streamQuery as cloudStream, queryVet as cloudQuery } from './api';
import { llamaCppClient, mlcClient } from './localInference';
import { modelManager } from './modelManager';

// ─── Types ────────────────────────────────────────────────────────────────────

export type QueryMode = 'cloud' | 'local_llamacpp' | 'local_mlc' | 'unavailable';

export interface RouterDecision {
  mode: QueryMode;
  reason: string;
}

// ─── Router ───────────────────────────────────────────────────────────────────

export class OfflineRouter {
  private _localReady = false;
  private _activeEngine: 'llamacpp' | 'mlc' | null = null;

  /**
   * Initialise local inference engine if model is downloaded.
   * Call this on app startup from _layout.tsx.
   */
  async init(): Promise<void> {
    const state = await modelManager.getModelState();

    if (state.status !== 'ready' || !state.localPath) {
      this._localReady = false;
      return;
    }

    // Select engine based on platform
    if (Platform.OS === 'ios') {
      try {
        await mlcClient.loadModel(state.localPath);
        if (mlcClient.isReady) {
          this._localReady = true;
          this._activeEngine = 'mlc';
          console.log('[Router] MLC engine ready (iOS Metal)');
          return;
        }
      } catch {
        console.warn('[Router] MLC failed, falling back to llama.cpp');
      }
    }

    // Android or iOS MLC fallback → llama.cpp
    try {
      await llamaCppClient.startServer(state.localPath);
      if (llamaCppClient.isRunning) {
        this._localReady = true;
        this._activeEngine = 'llamacpp';
        console.log('[Router] llama.cpp engine ready');
      }
    } catch (err) {
      console.warn('[Router] llama.cpp failed:', err);
      this._localReady = false;
    }
  }

  get isLocalReady(): boolean {
    return this._localReady;
  }

  get activeEngine(): 'llamacpp' | 'mlc' | null {
    return this._activeEngine;
  }

  // ── Route decision ──────────────────────────────────────────────────────

  async decide(): Promise<RouterDecision> {
    const online = await isOnline();

    if (online) {
      return {
        mode: 'cloud',
        reason: 'Online — using cloud AI for best accuracy',
      };
    }

    if (!this._localReady) {
      return {
        mode: 'unavailable',
        reason: 'Offline and no local model downloaded. Connect to internet or download the offline model in Settings.',
      };
    }

    if (this._activeEngine === 'mlc') {
      return { mode: 'local_mlc', reason: 'Offline — using on-device MLC model' };
    }

    return { mode: 'local_llamacpp', reason: 'Offline — using on-device llama.cpp model' };
  }

  // ── Unified stream query ──────────────────────────────────────────────────

  async streamQuery(
    query: string,
    onToken: (token: string) => void,
    onDone: () => void,
    onError: (err: Error) => void,
    onModeDecided?: (decision: RouterDecision) => void,
  ): Promise<void> {
    const decision = await this.decide();
    onModeDecided?.(decision);

    switch (decision.mode) {
      case 'cloud':
        return cloudStream(query, onToken, onDone, onError);

      case 'local_mlc':
        return mlcClient.streamQuery(query, onToken, onDone, onError);

      case 'local_llamacpp':
        return llamaCppClient.streamQuery(query, onToken, onDone, onError);

      case 'unavailable':
        onError(new Error(decision.reason));
        return;
    }
  }

  // ── Unified non-streaming query ───────────────────────────────────────────

  async query(
    query: string,
    options?: { top_k?: number; filter_species?: string; filter_source?: string }
  ): Promise<{ answer: string; mode: QueryMode; offline: boolean }> {
    const decision = await this.decide();

    switch (decision.mode) {
      case 'cloud': {
        const res = await cloudQuery(query, options);
        return { answer: res.answer, mode: 'cloud', offline: false };
      }

      case 'local_mlc': {
        const res = await mlcClient.query(query);
        return { answer: res.answer, mode: 'local_mlc', offline: true };
      }

      case 'local_llamacpp': {
        const res = await llamaCppClient.query(query);
        return { answer: res.answer, mode: 'local_llamacpp', offline: true };
      }

      case 'unavailable':
        throw new Error(decision.reason);
    }
  }
}

export const offlineRouter = new OfflineRouter();

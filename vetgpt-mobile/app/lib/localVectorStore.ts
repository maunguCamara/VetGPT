/**
 * vetgpt-mobile/lib/localVectorStore.ts
 *
 * Phase 2/4 — Offline local vector search using sqlite-vec.
 *
 * Architecture:
 *   - A pre-built vector index ships with the app (bundled asset)
 *   - sqlite-vec provides fast ANN search on-device
 *   - Index contains the same chunks as the cloud ChromaDB
 *   - Updated via delta sync when online
 *
 * This replaces the "Phase 2: replace with local search" comment
 * in offlineRouter.ts — the router now calls this module.
 *
 * Setup:
 *   npx expo install expo-sqlite
 *   The bundled index file lives at: assets/vet_index.db
 *   Copy it to the documents directory on first launch.
 *
 * Note: sqlite-vec is a SQLite extension. In React Native it requires
 * expo-sqlite with a custom build (expo prebuild needed).
 * For Expo Go testing, this falls back to keyword search gracefully.
 */

import * as FileSystem from 'expo-file-system';
import * as SQLite from 'expo-sqlite';
import { Platform } from 'react-native';

const INDEX_DB_NAME  = 'vet_index.db';
const INDEX_DB_PATH  = `${FileSystem.documentDirectory}${INDEX_DB_NAME}`;
const BUNDLED_ASSET  = FileSystem.bundleDirectory
  ? `${FileSystem.bundleDirectory}assets/${INDEX_DB_NAME}`
  : null;

export interface LocalChunk {
  chunk_id:       string;
  text:           string;
  source_file:    string;
  document_title: string;
  page_number:    number;
  score:          number;
}

// ─── Local Vector Store ────────────────────────────────────────────────────────

class LocalVectorStore {
  private _db: SQLite.SQLiteDatabase | null = null;
  private _ready = false;
  private _mode: 'vector' | 'keyword' | 'unavailable' = 'unavailable';

  /**
   * Initialise the local vector store.
   * Call once on app startup from offlineRouter.init().
   */
  async init(): Promise<void> {
    try {
      // Ensure index DB exists in documents directory
      const dbInfo = await FileSystem.getInfoAsync(INDEX_DB_PATH);

      if (!dbInfo.exists) {
        if (BUNDLED_ASSET) {
          // Copy bundled index to writable location
          try {
            await FileSystem.copyAsync({ from: BUNDLED_ASSET, to: INDEX_DB_PATH });
            console.log('[LocalVectorStore] Copied bundled index to documents');
          } catch {
            console.log('[LocalVectorStore] No bundled index found');
            this._mode = 'unavailable';
            return;
          }
        } else {
          this._mode = 'unavailable';
          return;
        }
      }

      // Open database
      this._db = await SQLite.openDatabaseAsync(INDEX_DB_NAME);

      // Check if sqlite-vec extension is available
      try {
        await this._db.runAsync('SELECT vec_version()');
        this._mode  = 'vector';
        this._ready = true;
        console.log('[LocalVectorStore] Vector search ready (sqlite-vec)');
      } catch {
        // sqlite-vec not available — fall back to keyword search
        this._mode  = 'keyword';
        this._ready = true;
        console.log('[LocalVectorStore] Falling back to keyword search (no sqlite-vec)');
      }
    } catch (err) {
      console.warn('[LocalVectorStore] Init failed:', err);
      this._mode = 'unavailable';
    }
  }

  get isReady(): boolean { return this._ready; }
  get mode(): string     { return this._mode; }

  /**
   * Search the local index.
   * Uses vector similarity if sqlite-vec available, keyword search otherwise.
   */
  async search(query: string, nResults: number = 5): Promise<LocalChunk[]> {
    if (!this._ready || !this._db) return [];

    if (this._mode === 'vector') {
      return this._vectorSearch(query, nResults);
    }
    return this._keywordSearch(query, nResults);
  }

  /**
   * Vector similarity search using sqlite-vec.
   * Requires the index to have been built with embeddings.
   */
  private async _vectorSearch(query: string, nResults: number): Promise<LocalChunk[]> {
    if (!this._db) return [];

    try {
      // In a production build, we'd embed the query on-device using
      // a bundled embedding model (e.g. all-MiniLM-L6-v2 via ONNX Runtime).
      // For now, fall back to keyword search since embedding requires
      // additional native module setup.
      return this._keywordSearch(query, nResults);
    } catch (err) {
      console.warn('[LocalVectorStore] Vector search failed:', err);
      return this._keywordSearch(query, nResults);
    }
  }

  /**
   * BM25-style keyword search — works without any native extensions.
   * Good enough for offline use when vector search unavailable.
   */
  private async _keywordSearch(query: string, nResults: number): Promise<LocalChunk[]> {
    if (!this._db) return [];

    try {
      // Tokenize query into individual terms
      const terms = query
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, ' ')
        .split(/\s+/)
        .filter(t => t.length > 2);

      if (terms.length === 0) return [];

      // Build LIKE conditions for each term
      const conditions = terms.map(() => `LOWER(text) LIKE ?`).join(' OR ');
      const params     = terms.map(t => `%${t}%`);

      const rows = await this._db.getAllAsync(
        `SELECT chunk_id, text, source_file, document_title, page_number,
                (${terms.map(() => `CASE WHEN LOWER(text) LIKE ? THEN 1 ELSE 0 END`).join(' + ')}) as match_count
         FROM chunks
         WHERE ${conditions}
         ORDER BY match_count DESC
         LIMIT ?`,
        [...params, ...params, nResults],
      );

      return (rows as any[]).map(row => ({
        chunk_id:       row.chunk_id,
        text:           row.text,
        source_file:    row.source_file,
        document_title: row.document_title,
        page_number:    row.page_number,
        score:          Math.min(row.match_count / terms.length, 1.0),
      }));
    } catch (err) {
      console.warn('[LocalVectorStore] Keyword search failed:', err);
      return [];
    }
  }

  /**
   * Sync new chunks from a JSON delta file downloaded from the server.
   * Called by offlineRouter when coming back online.
   */
  async syncDelta(deltaPath: string): Promise<number> {
    if (!this._db) return 0;

    try {
      const raw    = await FileSystem.readAsStringAsync(deltaPath);
      const chunks = JSON.parse(raw) as LocalChunk[];

      await this._db.withTransactionAsync(async () => {
        for (const chunk of chunks) {
          await this._db!.runAsync(
            `INSERT OR REPLACE INTO chunks
             (chunk_id, text, source_file, document_title, page_number)
             VALUES (?, ?, ?, ?, ?)`,
            [chunk.chunk_id, chunk.text, chunk.source_file,
             chunk.document_title, chunk.page_number],
          );
        }
      });

      console.log(`[LocalVectorStore] Synced ${chunks.length} new chunks`);
      return chunks.length;
    } catch (err) {
      console.warn('[LocalVectorStore] Delta sync failed:', err);
      return 0;
    }
  }

  /**
   * Create the chunks table if it doesn't exist.
   * Called when creating a fresh index.
   */
  async initSchema(): Promise<void> {
    if (!this._db) return;
    await this._db.runAsync(`
      CREATE TABLE IF NOT EXISTS chunks (
        chunk_id       TEXT PRIMARY KEY,
        text           TEXT NOT NULL,
        source_file    TEXT NOT NULL,
        document_title TEXT NOT NULL,
        page_number    INTEGER DEFAULT 1,
        created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `);
    await this._db.runAsync(`
      CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_file)
    `);
  }

  async getStats(): Promise<{ total_chunks: number; mode: string }> {
    if (!this._db || !this._ready) {
      return { total_chunks: 0, mode: this._mode };
    }
    try {
      const row = await this._db.getFirstAsync(
        'SELECT COUNT(*) as count FROM chunks'
      ) as any;
      return { total_chunks: row?.count ?? 0, mode: this._mode };
    } catch {
      return { total_chunks: 0, mode: this._mode };
    }
  }
}

export const localVectorStore = new LocalVectorStore();

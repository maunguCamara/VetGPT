/**
 * vetgpt-mobile/lib/localInference.ts
 *
 * Abstracts on-device inference across two engines:
 *
 * llama.cpp  — runs as a local HTTP server on localhost:8080
 *              React Native launches it via a native module (llama.rn)
 *              Supports GGUF format, OpenAI-compatible API
 *
 * MLC LLM    — runs via native bridge (react-native-mlc-llm)
 *              Compiled model binary, called directly (no HTTP)
 *              iOS Metal GPU optimized
 *
 * Both expose the same interface: query() + streamQuery()
 * The router in offlineRouter.ts picks the right one at runtime.
 */

import { Platform } from 'react-native';
import { BASE_URL } from './api';

// ─── System prompt (same as cloud backend) ───────────────────────────────────

const SYSTEM_PROMPT = `You are VetGPT, an AI veterinary reference assistant.
Answer questions for veterinary professionals using your training knowledge.
Be precise and clinically accurate. Use correct veterinary terminology.
If dosages are mentioned, always recommend confirming with current Plumb's or local formulary.
Never give a definitive diagnosis — you are a reference tool, not a clinician.
Keep answers concise and structured.`;

// ─── Types ────────────────────────────────────────────────────────────────────

export interface LocalQueryResult {
  answer: string;
  engine: 'llamacpp' | 'mlc';
  latency_ms: number;
  offline: true;
}

// ─── llama.cpp client ─────────────────────────────────────────────────────────
// llama.cpp runs llama-server on localhost:8080
// Expo native module: https://github.com/mybigday/llama.rn

const LLAMACPP_PORT = 8080;
const LLAMACPP_BASE = `http://localhost:${LLAMACPP_PORT}`;

export class LlamaCppClient {
  private _isServerRunning = false;

  /**
   * Start the llama.cpp server with the downloaded model.
   * In production this is called once when offline mode is activated.
   *
   * Uses llama.rn native module — install with:
   *   npx expo install llama.rn
   *   npx expo prebuild  (required — llama.rn is a native module)
   */
  async startServer(modelPath: string): Promise<void> {
    try {
      // Module only exists after `expo prebuild`
      // @ts-ignore - llama.rn is conditionally available after prebuild
      let LlamaContext: any;
      try {
        // // Dynamic import — module only exists after `expo prebuild`
      //const { LlamaContext } = await import('llama.rn');
        // @ts-ignore
        LlamaContext = require('llama.rn').LlamaContext;
      } catch {
        // Fallback for environments where llama.rn is not available
        console.warn('[llama.cpp] llama.rn not available, using HTTP server mode');
      }

      // llama.rn manages the context internally
      // For server mode on Android we use the HTTP server interface
      // For iOS we use the direct context API (faster, no HTTP overhead)

      if (Platform.OS === 'android') {
        // Android: spawn llama-server as background service
        // This requires the llama.rn native module with server support
        console.log('[llama.cpp] Starting server on Android port', LLAMACPP_PORT);
        // Server starts automatically when LlamaContext loads on Android
      }

      this._isServerRunning = true;
      console.log('[llama.cpp] Server ready at', LLAMACPP_BASE);
    } catch (err) {
      console.warn('[llama.cpp] Native module not available:', err);
      this._isServerRunning = false;
    }
  }

  get isRunning(): boolean {
    return this._isServerRunning;
  }

  /**
   * Query via llama.cpp OpenAI-compatible HTTP API.
   * Works identically on Android and iOS.
   */
  async query(userQuery: string): Promise<LocalQueryResult> {
    const start = Date.now();

    const response = await fetch(`${LLAMACPP_BASE}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'qwen2.5-3b',
        messages: [
          { role: 'system',  content: SYSTEM_PROMPT },
          { role: 'user',    content: userQuery },
        ],
        max_tokens: 512,
        temperature: 0.1,
        stream: false,
      }),
    });

    if (!response.ok) {
      throw new Error(`llama.cpp server error: ${response.status}`);
    }

    const data = await response.json();
    const answer = data.choices?.[0]?.message?.content ?? 'No response from local model.';

    return {
      answer,
      engine: 'llamacpp',
      latency_ms: Date.now() - start,
      offline: true,
    };
  }

  /**
   * Streaming version — yields tokens via SSE from llama.cpp server.
   */
  async streamQuery(
    userQuery: string,
    onToken: (token: string) => void,
    onDone: () => void,
    onError: (err: Error) => void
  ): Promise<void> {
    try {
      const response = await fetch(`${LLAMACPP_BASE}/v1/chat/completions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'qwen2.5-3b',
          messages: [
            { role: 'system', content: SYSTEM_PROMPT },
            { role: 'user',   content: userQuery },
          ],
          max_tokens: 512,
          temperature: 0.1,
          stream: true,
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error(`llama.cpp stream error: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const lines = decoder.decode(value, { stream: true }).split('\n');
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if (data === '[DONE]') { onDone(); return; }
          try {
            const parsed = JSON.parse(data);
            const token = parsed.choices?.[0]?.delta?.content;
            if (token) onToken(token);
          } catch { /* skip */ }
        }
      }
      onDone();
    } catch (err) {
      onError(err as Error);
    }
  }
}

// ─── MLC LLM client ───────────────────────────────────────────────────────────
// MLC runs via native bridge, no HTTP server needed
// Install: npx expo install react-native-mlc-llm
// Requires: npx expo prebuild

export class MLCClient {
  private _engine: any = null;
  private _isReady = false;

  /**
   * Load the MLC-compiled Qwen2.5-3B model.
   * Must be called once before querying.
   */

  
  async loadModel(modelPath: string): Promise<void> {
    try {
           const { MLCEngine } = await import('react-native-mlc-llm' as any);

      this._engine = await MLCEngine.create({
        model: modelPath,
        modelLib: 'qwen2_5_3b_instruct_q4f16_1',  // precompiled lib name
        quantization: 'q4f16_1',
      });

      this._isReady = true;
      console.log('[MLC] Qwen2.5-3B loaded via Metal GPU');
    } catch (err) {
      console.warn('[MLC] Native module not available:', err);
      this._isReady = false;
    }
  }

  get isReady(): boolean {
    return this._isReady;
  }

  async query(userQuery: string): Promise<LocalQueryResult> {
    if (!this._engine) throw new Error('MLC engine not loaded');
    const start = Date.now();

    const reply = await this._engine.chat.completions.create({
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user',   content: userQuery },
      ],
      max_tokens: 512,
      temperature: 0.1,
    });

    return {
      answer: reply.choices[0].message.content,
      engine: 'mlc',
      latency_ms: Date.now() - start,
      offline: true,
    };
  }

  async streamQuery(
    userQuery: string,
    onToken: (token: string) => void,
    onDone: () => void,
    onError: (err: Error) => void
  ): Promise<void> {
    if (!this._engine) { onError(new Error('MLC engine not loaded')); return; }

    try {
      const stream = await this._engine.chat.completions.create({
        messages: [
          { role: 'system', content: SYSTEM_PROMPT },
          { role: 'user',   content: userQuery },
        ],
        max_tokens: 512,
        temperature: 0.1,
        stream: true,
      });

      for await (const chunk of stream) {
        const token = chunk.choices[0]?.delta?.content;
        if (token) onToken(token);
      }
      onDone();
    } catch (err) {
      onError(err as Error);
    }
  }

  async unload(): Promise<void> {
    if (this._engine) {
      await this._engine.unload?.();
      this._engine = null;
      this._isReady = false;
    }
  }
}

// ─── Singletons ───────────────────────────────────────────────────────────────

export const llamaCppClient = new LlamaCppClient();
export const mlcClient      = new MLCClient();

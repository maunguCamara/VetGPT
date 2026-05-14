/**
 * vetgpt-mobile/lib/useSpeechRecognition.ts
 *
 * Multilingual speech-to-text hook.
 *
 * Supported languages:
 *   en-US  English
 *   sw-KE  Swahili (Kenya)
 *   fr-FR  French
 *   ar-SA  Arabic
 *   pt-PT  Portuguese
 *   es-ES  Spanish
 *   zh-CN  Chinese (Simplified)
 *
 * Fixes applied:
 *   - zh added to SPEECH_LOCALES and LOCALE_FLAG (was missing, caused type error)
 *   - useSpeechRecognitionEvent import removed (unused, caused lint warning)
 *   - Listeners are removed before adding new ones (prevented duplicate callbacks)
 *   - recognizerRef removed (was declared but never used)
 */

import { useState, useCallback, useRef } from 'react';
import { Platform } from 'react-native';
import type { SupportedLanguage } from './api';

// ── Language → BCP-47 locale map ─────────────────────────────────────────────

export const SPEECH_LOCALES: Record<SupportedLanguage, string> = {
  en: 'en-US',
  sw: 'sw-KE',
  fr: 'fr-FR',
  ar: 'ar-SA',
  pt: 'pt-PT',
  es: 'es-ES',
  zh: 'zh-CN',   // was missing — caused TypeScript error
};

export const LOCALE_FLAG: Record<SupportedLanguage, string> = {
  en: '🇺🇸',
  sw: '🇰🇪',
  fr: '🇫🇷',
  ar: '🇸🇦',
  pt: '🇵🇹',
  es: '🇪🇸',
  zh: '🇨🇳',   // was missing — caused TypeScript error
};

// ── Types ─────────────────────────────────────────────────────────────────────

export type SpeechState = 'idle' | 'listening' | 'processing' | 'error';

export interface UseSpeechRecognitionReturn {
  transcript:      string;
  state:           SpeechState;
  error:           string | null;
  isAvailable:     boolean;
  startListening:  (language?: SupportedLanguage) => Promise<void>;
  stopListening:   () => void;
  clearTranscript: () => void;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useSpeechRecognition(): UseSpeechRecognitionReturn {
  const [transcript, setTranscript]   = useState('');
  const [state, setState]             = useState<SpeechState>('idle');
  const [error, setError]             = useState<string | null>(null);
  const [isAvailable, setIsAvailable] = useState(
    Platform.OS === 'ios' || Platform.OS === 'android',
  );

  // Track active subscriptions so we can remove them before adding new ones
  // Prevents duplicate callbacks when startListening is called multiple times
  const subscriptions = useRef<any[]>([]);

  const removeAllListeners = useCallback(() => {
    for (const sub of subscriptions.current) {
      try { sub?.remove?.(); } catch {}
    }
    subscriptions.current = [];
  }, []);

  const startListening = useCallback(async (language: SupportedLanguage = 'en') => {
    setError(null);
    setTranscript('');

    if (Platform.OS === 'web') {
      setError('Speech recognition is not supported in the browser. Use the mobile app.');
      return;
    }

    try {
      // Dynamic import — works in Expo Go on device, fails gracefully on web
      const { ExpoSpeechRecognitionModule } =
        await import('@jamsch/expo-speech-recognition');

      // Permission
      const permission = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (!permission.granted) {
        setError('Microphone permission denied. Enable it in Settings → VetGPT.');
        return;
      }

      const locale = SPEECH_LOCALES[language] ?? 'en-US';

      // Remove any previous listeners before starting a new session
      // This was the listener leak bug — without this, every call to
      // startListening stacked a new set of listeners on top of the old ones
      removeAllListeners();

      setState('listening');

      ExpoSpeechRecognitionModule.start({
        lang:                        locale,
        interimResults:              true,
        maxAlternatives:             1,
        continuous:                  false,
        requiresOnDeviceRecognition: false,
        addsPunctuation:             true,
      });

      // Register listeners using the correct single-argument hook pattern.
      // ExpoSpeechRecognitionModule.addListener(eventName, handler) is TWO args —
      // but the library exposes useSpeechRecognitionEvent for React hooks instead.
      // For imperative use, subscribe via the EventEmitter directly.
      const { addSpeechRecognitionListener } = await import('@jamsch/expo-speech-recognition');

      const resultSub = addSpeechRecognitionListener(
        'result',
        (event: any) => {
          const text = event.results?.[0]?.transcript ?? '';
          setTranscript(text);
          if (event.isFinal) setState('idle');
        },
      );

      const errorSub = addSpeechRecognitionListener(
        'error',
        (event: any) => {
          const msg = event.message ?? event.code ?? 'Speech recognition failed';
          if (msg === 'no-speech') {
            setError('No speech detected. Tap the mic and speak clearly.');
          } else if (msg === 'network') {
            setError('Network required for speech recognition.');
          } else if (msg === 'not-allowed') {
            setError('Microphone permission denied.');
          } else {
            setError(msg);
          }
          setState('error');
        },
      );

      const endSub = addSpeechRecognitionListener(
        'end',
        () => { setState('idle'); },
      );

      subscriptions.current = [resultSub, errorSub, endSub];
      setIsAvailable(true);

    } catch (err: any) {
      const msg = err?.message ?? 'Speech recognition unavailable';
      if (msg.includes('not found') || msg.includes('Cannot find module')) {
        setError(
          'Speech recognition requires a native build.\n' +
          'Run: pnpm prebuild && pnpm android',
        );
        setIsAvailable(false);
      } else {
        setError(msg);
      }
      setState('error');
    }
  }, [removeAllListeners]);

  const stopListening = useCallback(async () => {
    try {
      const { ExpoSpeechRecognitionModule } =
        await import('@jamsch/expo-speech-recognition');
      ExpoSpeechRecognitionModule.stop();
    } catch {}
    removeAllListeners();
    setState('idle');
  }, [removeAllListeners]);

  const clearTranscript = useCallback(() => {
    setTranscript('');
    setError(null);
    setState('idle');
  }, []);

  return {
    transcript,
    state,
    error,
    isAvailable,
    startListening,
    stopListening,
    clearTranscript,
  };
}
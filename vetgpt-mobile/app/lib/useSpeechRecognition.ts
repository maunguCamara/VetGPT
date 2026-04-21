/**
 * vetgpt-mobile/lib/useSpeechRecognition.ts
 *
 * Multilingual speech-to-text hook.
 *
 * Supported languages (matching backend multilingual config):
 *   en-US  English
 *   sw-KE  Swahili (Kenya)
 *   fr-FR  French
 *   ar-SA  Arabic
 *   pt-PT  Portuguese
 *   es-ES  Spanish
 *   zh-CN  Chinese (Simplified)
 *
 * Library: @jamsch/expo-speech-recognition
 *   - Works in Expo Go on device (no prebuild needed for basic use)
 *   - Continuous mode supported
 *   - Interim results while speaking
 *   - Requires RECORD_AUDIO permission on Android
 *
 * Install:
 *   npx expo install @jamsch/expo-speech-recognition
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
  zh: 'zh-CN',
};

export const LOCALE_FLAG: Record<SupportedLanguage, string> = {
  en: '🇺🇸',
  sw: '🇰🇪',
  fr: '🇫🇷',
  ar: '🇸🇦',
  pt: '🇵🇹',
  es: '🇪🇸',
  zh: '🇨🇳',
};

// ── Types ─────────────────────────────────────────────────────────────────────

export type SpeechState = 'idle' | 'listening' | 'processing' | 'error';

export interface UseSpeechRecognitionReturn {
  transcript:   string;          // current recognised text (interim + final)
  state:        SpeechState;
  error:        string | null;
  isAvailable:  boolean;         // false in Expo Go web, true on device
  startListening: (language?: SupportedLanguage) => Promise<void>;
  stopListening:  () => void;
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
  const recognizerRef = useRef<any>(null);

  const startListening = useCallback(async (language: SupportedLanguage = 'en') => {
    setError(null);
    setTranscript('');

    // Web or simulator — not supported
    if (Platform.OS === 'web') {
      setError('Speech recognition is not supported in the browser. Use the mobile app.');
      return;
    }

    try {
      // Dynamic import — works in Expo Go on device
      const { ExpoSpeechRecognitionModule, useSpeechRecognitionEvent } =
        await import('@jamsch/expo-speech-recognition');

      // Request microphone permission
      const result = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (!result.granted) {
        setError('Microphone permission denied. Enable it in Settings.');
        return;
      }

      const locale = SPEECH_LOCALES[language] ?? 'en-US';

      setState('listening');

      ExpoSpeechRecognitionModule.start({
        lang:               locale,
        interimResults:     true,    // show partial results while speaking
        maxAlternatives:    1,
        continuous:         false,   // stop automatically after a pause
        requiresOnDeviceRecognition: false,
        addsPunctuation:    true,
      });

      // Results
      ExpoSpeechRecognitionModule.addListener('result', (event: any) => {
        const text = event.results?.[0]?.transcript ?? '';
        setTranscript(text);
        if (event.isFinal) {
          setState('idle');
        }
      });

      // Errors
      ExpoSpeechRecognitionModule.addListener('error', (event: any) => {
        const msg = event.message ?? event.code ?? 'Speech recognition failed';
        if (msg === 'no-speech') {
          setError('No speech detected. Tap the mic and speak clearly.');
        } else if (msg === 'network') {
          setError('Network required for speech recognition.');
        } else {
          setError(msg);
        }
        setState('error');
      });

      // End
      ExpoSpeechRecognitionModule.addListener('end', () => {
        setState('idle');
      });

      setIsAvailable(true);

    } catch (err: any) {
      const msg = err?.message ?? 'Speech recognition unavailable';
      if (msg.includes('not found') || msg.includes('Cannot find module')) {
        setError(
          'Speech recognition requires a native build.\n' +
          'Run: npx expo prebuild && npx expo run:android'
        );
        setIsAvailable(false);
      } else {
        setError(msg);
      }
      setState('error');
    }
  }, []);

  const stopListening = useCallback(async () => {
    try {
      const { ExpoSpeechRecognitionModule } =
        await import('@jamsch/expo-speech-recognition');
      ExpoSpeechRecognitionModule.stop();
    } catch {}
    setState('idle');
  }, []);

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

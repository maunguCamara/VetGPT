/**
 * vetgpt-mobile/app/(tabs)/chat.tsx
 *
 * Core chat screen:
 * - Streaming RAG responses from FastAPI
 * - Full citation display per answer
 * - Offline banner with graceful degradation
 * - Suggested starter questions
 * - Species / source filters
 */

import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator,
  SafeAreaView,
} from 'react-native';
import { useState, useRef, useCallback } from 'react';
import Markdown from 'react-native-markdown-display';
import { useChatStore, useAppStore, useAuthStore } from '../store';
import type { Message } from '../store';
import { offlineRouter } from '../lib/offlineRouter';
import { Colors, Spacing, Radius, Typography, Shadow } from '../constants/theme';
// ─── Suggested starter questions ─────────────────────────────────────────────

const SUGGESTED = [
  'Treatment for canine parvovirus?',
  'Feline hyperthyroidism drug dosages',
  'Bovine respiratory disease diagnosis',
  'Signs of equine colic',
  'Deworming protocol for sheep',
];

// ─── Sub-components ───────────────────────────────────────────────────────────

function OfflineBanner({ hasLocalModel }: { hasLocalModel: boolean }) {
  return (
    <View style={styles.offlineBanner}>
      <Text style={styles.offlineText}>
        {hasLocalModel
          ? '📶 Offline — using on-device AI (limited)'
          : '📶 Offline — connect to internet for full answers'}
      </Text>
    </View>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';

  return (
    <View style={[styles.bubbleRow, isUser && styles.bubbleRowUser]}>
      {!isUser && (
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>🐾</Text>
        </View>
      )}
      <View style={[styles.bubble, isUser ? styles.bubbleUser : styles.bubbleBot]}>
        {isUser ? (
          <Text style={styles.bubbleUserText}>{message.content}</Text>
        ) : (
          <>
            <Markdown style={markdownStyles}>
              {message.content || (message.isStreaming ? '▌' : '')}
            </Markdown>

            {message.isStreaming && (
              <ActivityIndicator
                size="small"
                color={Colors.primary}
                style={{ marginTop: 4 }}
              />
            )}

            {/* Citations */}
            {!message.isStreaming && message.citations && message.citations.length > 0 && (
              <View style={styles.citations}>
                <Text style={styles.citationsLabel}>Sources</Text>
                {message.citations.slice(0, 3).map((c, i) => (
                  <View key={i} style={styles.citationRow}>
                    <Text style={styles.citationScore}>
                      {Math.round(c.score * 100)}%
                    </Text>
                    <Text style={styles.citationText} numberOfLines={2}>
                      {c.document_title} — p.{c.page_number}
                    </Text>
                  </View>
                ))}
              </View>
            )}

            {/* Disclaimer */}
            {!message.isStreaming && message.disclaimer && (
              <Text style={styles.disclaimer}>{message.disclaimer}</Text>
            )}
          </>
        )}
      </View>
    </View>
  );
}

function SuggestedQuestions({ onPress }: { onPress: (q: string) => void }) {
  return (
    <View style={styles.suggestions}>
      <Text style={styles.suggestionsLabel}>Suggested questions</Text>
      {SUGGESTED.map((q) => (
        <TouchableOpacity
          key={q}
          style={styles.suggestionChip}
          onPress={() => onPress(q)}
          activeOpacity={0.7}
        >
          <Text style={styles.suggestionText}>{q}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

// ─── Main Screen ──────────────────────────────────────────────────────────────

export default function ChatScreen() {
  const [input, setInput] = useState('');
  const flatListRef = useRef<FlatList>(null);

  const { messages, isQuerying, addMessage, updateLastMessage, setQuerying, newSession } = useChatStore();
  const { isOnline, hasLocalModel, filterSpecies, filterSource } = useAppStore();
  const { user } = useAuthStore();

  const isPremium = user?.tier === 'premium' || user?.tier === 'clinic';

  const scrollToBottom = useCallback(() => {
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
  }, []);

  async function sendMessage(text?: string) {
    const query = (text ?? input).trim();
    if (!query || isQuerying) return;
    setInput('');

    // Add user message
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: query,
      timestamp: new Date(),
    };
    addMessage(userMsg);
    scrollToBottom();

    // Add empty bot message (will be streamed into)
    const botMsg: Message = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: '',
      isStreaming: true,
      timestamp: new Date(),
    };
    addMessage(botMsg);
    setQuerying(true);
    scrollToBottom();

    if (!isOnline && !hasLocalModel) {
      updateLastMessage(
        'You are offline and no local model is downloaded. ' +
        'Connect to the internet to use VetGPT.',
        true
      );
      setQuerying(false);
      return;
    }

    await offlineRouter.streamQuery(
      query,
      (token) => {
        updateLastMessage(token);
        scrollToBottom();
      },
      () => {
        setQuerying(false);
        scrollToBottom();
      },
      (err) => {
        updateLastMessage(
          err.message.includes('offline') || err.message.includes('internet')
            ? err.message
            : `Error: ${err.message}. Please try again.`,
          true
        );
        setQuerying(false);
      },
      (decision) => {
        // Optionally show which mode is being used
        console.log('[Chat] Query mode:', decision.mode);
      }
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>VetGPT</Text>
          <Text style={styles.headerSub}>
            {isOnline ? '🟢 Online' : '🔴 Offline'}
            {filterSpecies ? `  ·  ${filterSpecies}` : ''}
          </Text>
        </View>
        <TouchableOpacity onPress={newSession} style={styles.newChatBtn}>
          <Text style={styles.newChatText}>New chat</Text>
        </TouchableOpacity>
      </View>

      {!isOnline && <OfflineBanner hasLocalModel={hasLocalModel} />}

      {/* Messages */}
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={0}
      >
        <FlatList
          ref={flatListRef}
          data={messages}
          keyExtractor={(m) => m.id}
          contentContainerStyle={styles.messageList}
          ListEmptyComponent={
            <SuggestedQuestions onPress={(q) => sendMessage(q)} />
          }
          renderItem={({ item }) => <MessageBubble message={item} />}
          onContentSizeChange={scrollToBottom}
        />

        {/* Input bar */}
        <View style={styles.inputBar}>
          {isPremium && (
            <TouchableOpacity style={styles.imageBtn}>
              <Text style={styles.imageBtnText}>📷</Text>
            </TouchableOpacity>
          )}
          <TextInput
            style={styles.input}
            placeholder="Ask a veterinary question..."
            placeholderTextColor={Colors.textMuted}
            value={input}
            onChangeText={setInput}
            multiline
            maxLength={2000}
            onSubmitEditing={() => sendMessage()}
            returnKeyType="send"
            blurOnSubmit={false}
          />
          <TouchableOpacity
            style={[styles.sendBtn, (!input.trim() || isQuerying) && styles.sendBtnDisabled]}
            onPress={() => sendMessage()}
            disabled={!input.trim() || isQuerying}
            activeOpacity={0.8}
          >
            {isQuerying
              ? <ActivityIndicator size="small" color="#fff" />
              : <Text style={styles.sendIcon}>↑</Text>
            }
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.background },
  flex: { flex: 1 },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    paddingTop: Spacing.md,
  },
  headerTitle: { ...Typography.h3, color: '#fff' },
  headerSub: { ...Typography.caption, color: 'rgba(255,255,255,0.75)', marginTop: 2 },
  newChatBtn: {
    backgroundColor: 'rgba(255,255,255,0.2)',
    borderRadius: Radius.full,
    paddingHorizontal: Spacing.md,
    paddingVertical: 6,
  },
  newChatText: { ...Typography.label, color: '#fff' },

  offlineBanner: {
    backgroundColor: Colors.error,
    paddingHorizontal: Spacing.md,
    paddingVertical: 7,
  },
  offlineText: { ...Typography.caption, color: '#fff', textAlign: 'center' },

  messageList: { padding: Spacing.md, paddingBottom: Spacing.xl },

  bubbleRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    marginBottom: Spacing.md,
  },
  bubbleRowUser: { flexDirection: 'row-reverse' },

  avatar: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: Colors.primaryLight,
    alignItems: 'center', justifyContent: 'center',
    marginRight: 8,
  },
  avatarText: { fontSize: 16 },

  bubble: {
    maxWidth: '80%',
    borderRadius: Radius.lg,
    padding: Spacing.md,
    ...Shadow.sm,
  },
  bubbleUser: {
    backgroundColor: Colors.bubbleUser,
    borderBottomRightRadius: 4,
  },
  bubbleBot: {
    backgroundColor: Colors.bubbleBot,
    borderBottomLeftRadius: 4,
  },
  bubbleUserText: { ...Typography.body, color: Colors.bubbleUserText },

  citations: {
    marginTop: Spacing.sm,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
    paddingTop: Spacing.sm,
  },
  citationsLabel: { ...Typography.label, color: Colors.textMuted, marginBottom: 4 },
  citationRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 3,
    gap: 6,
  },
  citationScore: {
    ...Typography.caption,
    color: Colors.primary,
    fontWeight: '700',
    minWidth: 32,
  },
  citationText: { ...Typography.caption, color: Colors.textSecondary, flex: 1 },

  disclaimer: {
    ...Typography.caption,
    color: Colors.warning,
    marginTop: Spacing.sm,
    fontStyle: 'italic',
  },

  suggestions: { paddingVertical: Spacing.lg },
  suggestionsLabel: {
    ...Typography.label,
    color: Colors.textMuted,
    marginBottom: Spacing.sm,
    textAlign: 'center',
  },
  suggestionChip: {
    backgroundColor: Colors.surface,
    borderRadius: Radius.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.md,
    marginBottom: Spacing.sm,
    ...Shadow.sm,
  },
  suggestionText: { ...Typography.body, color: Colors.primary },

  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    padding: Spacing.sm,
    backgroundColor: Colors.surface,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    gap: Spacing.sm,
  },
  imageBtn: {
    width: 40, height: 40,
    borderRadius: Radius.md,
    backgroundColor: Colors.premiumBg,
    alignItems: 'center', justifyContent: 'center',
  },
  imageBtnText: { fontSize: 20 },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radius.lg,
    paddingHorizontal: Spacing.md,
    paddingVertical: 10,
    ...Typography.body,
    color: Colors.textPrimary,
    maxHeight: 120,
    backgroundColor: Colors.background,
  },
  sendBtn: {
    width: 40, height: 40,
    borderRadius: Radius.full,
    backgroundColor: Colors.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  sendBtnDisabled: { backgroundColor: Colors.borderStrong },
  sendIcon: { color: '#fff', fontSize: 20, fontWeight: '700' },
});

const markdownStyles: any = {
  body: { ...Typography.body, color: Colors.bubbleBotText },
  heading1: { ...Typography.h3, color: Colors.textPrimary, marginVertical: 6 },
  heading2: { ...Typography.h4, color: Colors.textPrimary, marginVertical: 4 },
  strong: { fontWeight: '700' },
  code_inline: {
    backgroundColor: Colors.surfaceAlt,
    borderRadius: 4,
    fontFamily: 'monospace',
    fontSize: 13,
    paddingHorizontal: 4,
  },
  bullet_list: { marginVertical: 4 },
  list_item: { marginVertical: 2 },
};

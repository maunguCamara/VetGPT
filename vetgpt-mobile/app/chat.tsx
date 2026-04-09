/**
 * vetgpt-mobile/app/(tabs)/chat.tsx
 * Core RAG chat — streaming, citations, offline banner, suggested questions.
 * Fixes: Enter sends not newline, import types, welcome screen, error display.
 */

import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator,
  SafeAreaView, Keyboard,
} from 'react-native';
import { useState, useRef, useCallback } from 'react';
import Markdown from 'react-native-markdown-display';
import { useChatStore, useAppStore, useAuthStore } from '../../store';
import type { Message } from '../../store';
import { offlineRouter } from '../../lib/offlineRouter';
import { Colors, Spacing, Radius, Typography, Shadow } from '../../constants/theme';

const SUGGESTED = [
  'Clinical signs of canine parvovirus?',
  'Feline hyperthyroidism drug dosages',
  'Bovine respiratory disease diagnosis',
  'Signs of equine colic',
  'Deworming protocol for sheep',
];

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
            {message.isError ? (
              <Text style={styles.errorText}>{message.content}</Text>
            ) : (
              <Markdown style={markdownStyles}>
                {message.content || (message.isStreaming ? '▌' : '')}
              </Markdown>
            )}
            {message.isStreaming && (
              <ActivityIndicator size="small" color={Colors.primary} style={{ marginTop: 4 }} />
            )}
            {!message.isStreaming && message.citations && message.citations.length > 0 && (
              <View style={styles.citations}>
                <Text style={styles.citationsLabel}>Sources</Text>
                {message.citations.slice(0, 3).map((c, i) => (
                  <View key={i} style={styles.citationRow}>
                    <Text style={styles.citationScore}>{Math.round(c.score * 100)}%</Text>
                    <Text style={styles.citationText} numberOfLines={2}>
                      {c.document_title} — p.{c.page_number}
                    </Text>
                  </View>
                ))}
              </View>
            )}
            {!message.isStreaming && message.disclaimer && (
              <Text style={styles.disclaimer}>{message.disclaimer}</Text>
            )}
          </>
        )}
      </View>
    </View>
  );
}

function WelcomeScreen({ onPress }: { onPress: (q: string) => void }) {
  return (
    <View style={styles.welcome}>
      <View style={styles.welcomeBox}>
        <Text style={styles.welcomeEmoji}>🐾</Text>
        <Text style={styles.welcomeTitle}>VetGPT</Text>
        <Text style={styles.welcomeSub}>
          AI veterinary reference assistant. Ask about diseases,
          drug dosages, procedures, or diagnostics.
        </Text>
      </View>
      <Text style={styles.suggestionsLabel}>Try asking</Text>
      {SUGGESTED.map((q) => (
        <TouchableOpacity
          key={q}
          style={styles.suggestionChip}
          onPress={() => onPress(q)}
          activeOpacity={0.7}
        >
          <Text style={styles.suggestionText}>{q}</Text>
          <Text style={styles.suggestionArrow}>→</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

export default function ChatScreen() {
  const [input, setInput] = useState('');
  const flatListRef = useRef<FlatList>(null);

  const {
    messages, isQuerying,
    addMessage, updateLastMessage, setQuerying, newSession,
  } = useChatStore();
  const { isOnline, hasLocalModel, filterSpecies } = useAppStore();
  const { user } = useAuthStore();

  const isPremium = user?.tier === 'premium' || user?.tier === 'clinic';

  const scrollToBottom = useCallback(() => {
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 80);
  }, []);

  async function sendMessage(text?: string) {
    const query = (text ?? input).trim();
    if (!query || isQuerying) return;

    setInput('');
    Keyboard.dismiss();

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: query,
      timestamp: new Date(),
    };
    addMessage(userMsg);
    scrollToBottom();

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
        'Connect to the internet or download the offline model in Settings.',
        true,
      );
      setQuerying(false);
      return;
    }

    await offlineRouter.streamQuery(
      query,
      (token) => { updateLastMessage(token); scrollToBottom(); },
      () => { setQuerying(false); scrollToBottom(); },
      (err) => {
        updateLastMessage(
          err.message.includes('offline') || err.message.includes('internet')
            ? err.message
            : 'Something went wrong. Please try again.',
          true,
        );
        setQuerying(false);
      },
      (decision) => console.log('[Chat] mode:', decision.mode),
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>VetGPT</Text>
          <Text style={styles.headerSub}>
            {isOnline ? '🟢 Online' : '🔴 Offline'}
            {filterSpecies ? `  ·  ${filterSpecies}` : ''}
          </Text>
        </View>
        <TouchableOpacity onPress={newSession} style={styles.newChatBtn} activeOpacity={0.8}>
          <Text style={styles.newChatText}>+ New</Text>
        </TouchableOpacity>
      </View>

      {!isOnline && <OfflineBanner hasLocalModel={hasLocalModel} />}

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <FlatList
          ref={flatListRef}
          data={messages}
          keyExtractor={(m) => m.id}
          contentContainerStyle={styles.messageList}
          ListEmptyComponent={<WelcomeScreen onPress={sendMessage} />}
          renderItem={({ item }) => <MessageBubble message={item} />}
          onContentSizeChange={scrollToBottom}
          keyboardShouldPersistTaps="handled"
        />

        <View style={styles.inputBar}>
          {isPremium && (
            <TouchableOpacity style={styles.imageBtn} activeOpacity={0.7}>
              <Text style={styles.imageBtnText}>📷</Text>
            </TouchableOpacity>
          )}
          <TextInput
            style={styles.input}
            placeholder="Ask a veterinary question..."
            placeholderTextColor={Colors.textMuted}
            value={input}
            onChangeText={setInput}
            multiline={false}
            maxLength={2000}
            returnKeyType="send"
            onSubmitEditing={() => sendMessage()}
            blurOnSubmit={false}
            editable={!isQuerying}
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

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.background },
  flex: { flex: 1 },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm, paddingTop: Spacing.md,
  },
  headerTitle: { ...Typography.h3, color: '#fff' },
  headerSub: { ...Typography.caption, color: 'rgba(255,255,255,0.75)', marginTop: 2 },
  newChatBtn: {
    backgroundColor: 'rgba(255,255,255,0.2)',
    borderRadius: Radius.full, paddingHorizontal: Spacing.md, paddingVertical: 6,
  },
  newChatText: { ...Typography.label, color: '#fff' },
  offlineBanner: { backgroundColor: Colors.error, paddingHorizontal: Spacing.md, paddingVertical: 7 },
  offlineText: { ...Typography.caption, color: '#fff', textAlign: 'center' },
  messageList: { padding: Spacing.md, paddingBottom: Spacing.xl, flexGrow: 1 },
  bubbleRow: { flexDirection: 'row', alignItems: 'flex-end', marginBottom: Spacing.md },
  bubbleRowUser: { flexDirection: 'row-reverse' },
  avatar: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: Colors.primaryLight,
    alignItems: 'center', justifyContent: 'center', marginRight: 8,
  },
  avatarText: { fontSize: 16 },
  bubble: { maxWidth: '82%', borderRadius: Radius.lg, padding: Spacing.md, ...Shadow.sm },
  bubbleUser: { backgroundColor: Colors.bubbleUser, borderBottomRightRadius: 4 },
  bubbleBot: { backgroundColor: Colors.bubbleBot, borderBottomLeftRadius: 4 },
  bubbleUserText: { ...Typography.body, color: Colors.bubbleUserText },
  errorText: { ...Typography.body, color: Colors.error },
  citations: {
    marginTop: Spacing.sm, borderTopWidth: 1, borderTopColor: Colors.divider, paddingTop: Spacing.sm,
  },
  citationsLabel: { ...Typography.label, color: Colors.textMuted, marginBottom: 4 },
  citationRow: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 3, gap: 6 },
  citationScore: { ...Typography.caption, color: Colors.primary, fontWeight: '700', minWidth: 32 },
  citationText: { ...Typography.caption, color: Colors.textSecondary, flex: 1 },
  disclaimer: { ...Typography.caption, color: Colors.warning, marginTop: Spacing.sm, fontStyle: 'italic' },
  welcome: { flexGrow: 1 },
  welcomeBox: { alignItems: 'center', paddingVertical: Spacing.xl, paddingHorizontal: Spacing.lg },
  welcomeEmoji: { fontSize: 52, marginBottom: Spacing.sm },
  welcomeTitle: { ...Typography.h2, color: Colors.primary, marginBottom: Spacing.xs },
  welcomeSub: { ...Typography.body, color: Colors.textSecondary, textAlign: 'center' },
  suggestionsLabel: {
    ...Typography.label, color: Colors.textMuted,
    marginBottom: Spacing.sm, marginHorizontal: Spacing.md,
  },
  suggestionChip: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: Colors.surface, borderRadius: Radius.lg,
    borderWidth: 1, borderColor: Colors.border,
    paddingHorizontal: Spacing.md, paddingVertical: Spacing.md,
    marginHorizontal: Spacing.md, marginBottom: Spacing.sm, ...Shadow.sm,
  },
  suggestionText: { ...Typography.body, color: Colors.textPrimary, flex: 1 },
  suggestionArrow: { ...Typography.body, color: Colors.primary, marginLeft: Spacing.sm },
  inputBar: {
    flexDirection: 'row', alignItems: 'center',
    padding: Spacing.sm, backgroundColor: Colors.surface,
    borderTopWidth: 1, borderTopColor: Colors.border, gap: Spacing.sm,
  },
  imageBtn: {
    width: 40, height: 40, borderRadius: Radius.md,
    backgroundColor: Colors.premiumBg, alignItems: 'center', justifyContent: 'center',
  },
  imageBtnText: { fontSize: 20 },
  input: {
    flex: 1, borderWidth: 1, borderColor: Colors.border, borderRadius: Radius.lg,
    paddingHorizontal: Spacing.md,
    paddingVertical: Platform.OS === 'ios' ? 12 : 8,
    ...Typography.body, color: Colors.textPrimary, backgroundColor: Colors.background,
  },
  sendBtn: {
    width: 40, height: 40, borderRadius: Radius.full,
    backgroundColor: Colors.primary, alignItems: 'center', justifyContent: 'center',
  },
  sendBtnDisabled: { backgroundColor: Colors.borderStrong },
  sendIcon: { color: '#fff', fontSize: 20, fontWeight: '700' },
});

const markdownStyles: any = {
  body: { ...Typography.body, color: Colors.bubbleBotText },
  heading2: { ...Typography.h4, color: Colors.textPrimary, marginVertical: 4 },
  strong: { fontWeight: '700' },
  code_inline: {
    backgroundColor: Colors.surfaceAlt, borderRadius: 4,
    fontFamily: 'monospace', fontSize: 13, paddingHorizontal: 4,
  },
};

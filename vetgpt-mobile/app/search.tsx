/**
 * vetgpt-mobile/app/(tabs)/search.tsx
 * Direct vector search with working species/source filter logic.
 */

import {
  View, Text, TextInput, FlatList, TouchableOpacity,
  StyleSheet, ActivityIndicator, SafeAreaView, ScrollView,
  KeyboardAvoidingView, Platform, Keyboard,
} from 'react-native';
import { useState, useRef } from 'react';
import { queryVet } from '../../lib/api';
import type { QueryResponse, Citation } from '../../lib/api';
import { useAppStore } from '../../store';
import { Colors, Spacing, Radius, Typography, Shadow } from '../../constants/theme';

const SPECIES_FILTERS = ['All', 'Canine', 'Feline', 'Bovine', 'Equine', 'Ovine', 'Porcine', 'Exotic'];
const SOURCE_FILTERS  = ['All', 'WikiVet', 'PubMed', 'FAO', 'eClinPath'];

function FilterChip({
  label, active, onPress, accent,
}: { label: string; active: boolean; onPress: () => void; accent?: boolean }) {
  return (
    <TouchableOpacity
      style={[styles.chip, active && styles.chipActive, accent && styles.chipAccent]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
    </TouchableOpacity>
  );
}

function CitationCard({ item, index }: { item: Citation; index: number }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <TouchableOpacity
      style={styles.citationCard}
      onPress={() => setExpanded((e) => !e)}
      activeOpacity={0.85}
    >
      <View style={styles.citationHeader}>
        <View style={styles.citationRankBadge}>
          <Text style={styles.citationRankText}>#{index + 1}</Text>
        </View>
        <View style={styles.citationMeta}>
          <Text style={styles.citationTitle} numberOfLines={2}>{item.document_title}</Text>
          <Text style={styles.citationPage}>Page {item.page_number}</Text>
        </View>
        <View style={styles.scoreBadge}>
          <Text style={styles.scoreText}>{Math.round(item.score * 100)}%</Text>
        </View>
      </View>
      <Text
        style={styles.citationExcerpt}
        numberOfLines={expanded ? undefined : 3}
      >
        {item.excerpt}
      </Text>
      <Text style={styles.expandHint}>{expanded ? 'Show less ↑' : 'Show more ↓'}</Text>
    </TouchableOpacity>
  );
}

export default function SearchScreen() {
  const [query, setQuery]         = useState('');
  const [species, setSpecies]     = useState('All');
  const [source, setSource]       = useState('All');
  const [loading, setLoading]     = useState(false);
  const [result, setResult]       = useState<QueryResponse | null>(null);
  const [error, setError]         = useState('');
  const inputRef                  = useRef<TextInput>(null);

  const { setFilterSpecies, setFilterSource } = useAppStore();

  async function handleSearch() {
    const q = query.trim();
    if (!q) {
      inputRef.current?.focus();
      return;
    }
    Keyboard.dismiss();
    setLoading(true);
    setError('');
    setResult(null);

    try {
      const res = await queryVet(q, {
        top_k: 8,
        filter_species: species !== 'All' ? species.toLowerCase() : undefined,
        filter_source:  source  !== 'All' ? source.toLowerCase()  : undefined,
      });
      setResult(res);

      // Sync filters to global store so chat uses same filters
      setFilterSpecies(species !== 'All' ? species.toLowerCase() : null);
      setFilterSource(source   !== 'All' ? source.toLowerCase()  : null);
    } catch (err: any) {
      setError(
        err.message === 'offline'
          ? 'You are offline. Connect to internet to search the knowledge base.'
          : err.message?.includes('401')
          ? 'Please sign in to search.'
          : `Search failed: ${err.message}`
      );
    } finally {
      setLoading(false);
    }
  }

  function clearSearch() {
    setQuery('');
    setResult(null);
    setError('');
    setSpecies('All');
    setSource('All');
    inputRef.current?.focus();
  }

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.title}>Search Manuals</Text>
        <Text style={styles.subtitle}>Search indexed veterinary references</Text>
      </View>

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        {/* Search bar */}
        <View style={styles.searchBar}>
          <TextInput
            ref={inputRef}
            style={styles.searchInput}
            placeholder="e.g. bovine respiratory disease treatment"
            placeholderTextColor={Colors.textMuted}
            value={query}
            onChangeText={setQuery}
            returnKeyType="search"
            onSubmitEditing={handleSearch}
            autoCorrect={false}
            autoCapitalize="none"
          />
          {query.length > 0 && (
            <TouchableOpacity onPress={clearSearch} style={styles.clearBtn}>
              <Text style={styles.clearBtnText}>✕</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity
            style={[styles.searchBtn, loading && { opacity: 0.6 }]}
            onPress={handleSearch}
            disabled={loading}
            activeOpacity={0.85}
          >
            {loading
              ? <ActivityIndicator size="small" color="#fff" />
              : <Text style={styles.searchBtnText}>Search</Text>
            }
          </TouchableOpacity>
        </View>

        {/* Species filters */}
        <View>
          <Text style={styles.filterLabel}>Species</Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.filterRow}
          >
            {SPECIES_FILTERS.map((s) => (
              <FilterChip
                key={s}
                label={s}
                active={species === s}
                onPress={() => setSpecies(s)}
              />
            ))}
          </ScrollView>

          <Text style={styles.filterLabel}>Source</Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.filterRow}
          >
            {SOURCE_FILTERS.map((s) => (
              <FilterChip
                key={s}
                label={s}
                active={source === s}
                onPress={() => setSource(s)}
                accent
              />
            ))}
          </ScrollView>
        </View>

        {/* Error */}
        {!!error && (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {/* Empty state */}
        {!result && !loading && !error && (
          <View style={styles.emptyState}>
            <Text style={styles.emptyEmoji}>🔍</Text>
            <Text style={styles.emptyTitle}>Search your vet library</Text>
            <Text style={styles.emptySub}>
              Search across WikiVet, PubMed, FAO, eClinPath and your uploaded PDFs.
              Use species and source filters to narrow results.
            </Text>
          </View>
        )}

        {/* Results */}
        {result && (
          <FlatList
            data={result.citations}
            keyExtractor={(_, i) => i.toString()}
            contentContainerStyle={styles.results}
            keyboardShouldPersistTaps="handled"
            ListHeaderComponent={
              <View style={styles.answerCard}>
                <View style={styles.answerHeader}>
                  <Text style={styles.answerLabel}>AI Summary</Text>
                  <Text style={styles.answerMeta}>
                    {result.chunks_retrieved} sources · {result.latency_ms}ms
                  </Text>
                </View>
                <Text style={styles.answerText}>{result.answer}</Text>
                <Text style={styles.disclaimer}>{result.disclaimer}</Text>
              </View>
            }
            ListFooterComponent={
              result.citations.length === 0
                ? (
                  <View style={styles.noResults}>
                    <Text style={styles.noResultsText}>
                      No matching chunks found. Try different keywords or remove filters.
                    </Text>
                  </View>
                )
                : null
            }
            renderItem={({ item, index }) => (
              <CitationCard item={item} index={index} />
            )}
          />
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.background },
  flex: { flex: 1 },
  header: {
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.md, paddingTop: Spacing.lg, paddingBottom: Spacing.md,
  },
  title: { ...Typography.h3, color: '#fff' },
  subtitle: { ...Typography.caption, color: 'rgba(255,255,255,0.75)', marginTop: 2 },

  searchBar: {
    flexDirection: 'row', alignItems: 'center', gap: Spacing.sm,
    padding: Spacing.md, backgroundColor: Colors.surface,
    borderBottomWidth: 1, borderBottomColor: Colors.border,
  },
  searchInput: {
    flex: 1, borderWidth: 1, borderColor: Colors.border, borderRadius: Radius.md,
    paddingHorizontal: Spacing.md, paddingVertical: 10,
    ...Typography.body, color: Colors.textPrimary, backgroundColor: Colors.background,
  },
  clearBtn: {
    position: 'absolute', right: 100, padding: 8,
  },
  clearBtnText: { ...Typography.body, color: Colors.textMuted },
  searchBtn: {
    backgroundColor: Colors.primary, borderRadius: Radius.md,
    paddingHorizontal: Spacing.md, paddingVertical: 10,
  },
  searchBtnText: { ...Typography.label, color: '#fff' },

  filterLabel: {
    ...Typography.caption, color: Colors.textMuted, fontWeight: '600',
    marginLeft: Spacing.md, marginTop: Spacing.sm, marginBottom: 2,
  },
  filterRow: { paddingHorizontal: Spacing.md, paddingVertical: 6, gap: Spacing.sm },
  chip: {
    borderRadius: Radius.full, borderWidth: 1, borderColor: Colors.border,
    paddingHorizontal: Spacing.md, paddingVertical: 5, backgroundColor: Colors.surface,
  },
  chipActive: { backgroundColor: Colors.primary, borderColor: Colors.primary },
  chipAccent: { borderColor: Colors.accent + '66' },
  chipText: { ...Typography.label, color: Colors.textSecondary },
  chipTextActive: { color: '#fff' },

  errorBox: {
    margin: Spacing.md, padding: Spacing.md,
    backgroundColor: '#FEE', borderRadius: Radius.md,
    borderWidth: 1, borderColor: Colors.error,
  },
  errorText: { ...Typography.body, color: Colors.error },

  emptyState: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: Spacing.xl },
  emptyEmoji: { fontSize: 48, marginBottom: Spacing.md },
  emptyTitle: { ...Typography.h3, color: Colors.textPrimary, marginBottom: Spacing.sm },
  emptySub: { ...Typography.body, color: Colors.textSecondary, textAlign: 'center' },

  results: { padding: Spacing.md, gap: Spacing.md },

  answerCard: {
    backgroundColor: Colors.surface, borderRadius: Radius.lg,
    padding: Spacing.md, borderLeftWidth: 4, borderLeftColor: Colors.primary,
    marginBottom: Spacing.sm, ...Shadow.sm,
  },
  answerHeader: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', marginBottom: Spacing.sm,
  },
  answerLabel: { ...Typography.label, color: Colors.primary },
  answerMeta: { ...Typography.caption, color: Colors.textMuted },
  answerText: { ...Typography.body, color: Colors.textPrimary },
  disclaimer: { ...Typography.caption, color: Colors.warning, marginTop: Spacing.sm, fontStyle: 'italic' },

  citationCard: {
    backgroundColor: Colors.surface, borderRadius: Radius.lg,
    padding: Spacing.md, ...Shadow.sm,
  },
  citationHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: Spacing.sm, marginBottom: Spacing.sm },
  citationRankBadge: {
    backgroundColor: Colors.surfaceAlt, borderRadius: Radius.sm,
    width: 28, height: 28, alignItems: 'center', justifyContent: 'center',
  },
  citationRankText: { ...Typography.label, color: Colors.textSecondary },
  citationMeta: { flex: 1 },
  citationTitle: { ...Typography.h4, color: Colors.textPrimary },
  citationPage: { ...Typography.caption, color: Colors.textMuted, marginTop: 2 },
  scoreBadge: {
    backgroundColor: Colors.primary + '18', borderRadius: Radius.full,
    paddingHorizontal: 8, paddingVertical: 3,
  },
  scoreText: { ...Typography.caption, color: Colors.primary, fontWeight: '700' },
  citationExcerpt: { ...Typography.bodySmall, color: Colors.textSecondary },
  expandHint: { ...Typography.caption, color: Colors.primary, marginTop: Spacing.xs },

  noResults: {
    padding: Spacing.lg, alignItems: 'center',
  },
  noResultsText: { ...Typography.body, color: Colors.textMuted, textAlign: 'center' },
});

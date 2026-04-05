/**
 * vetgpt-mobile/app/(tabs)/search.tsx
 * Direct vector search with species and source filters.
 */

import {
  View, Text, TextInput, FlatList, TouchableOpacity,
  StyleSheet, ActivityIndicator, SafeAreaView,
} from 'react-native';
import { useState } from 'react';
import { queryVet, QueryResponse } from '../../lib/api';
import { Colors, Spacing, Radius, Typography, Shadow } from '../../constants/theme';

const SPECIES_FILTERS = ['All', 'Canine', 'Feline', 'Bovine', 'Equine', 'Ovine', 'Porcine', 'Exotic'];
const SOURCE_FILTERS  = ['All', 'WikiVet', 'PubMed', 'FAO', 'Plumbs'];

export default function SearchScreen() {
  const [query, setQuery]         = useState('');
  const [species, setSpecies]     = useState('All');
  const [source, setSource]       = useState('All');
  const [loading, setLoading]     = useState(false);
  const [result, setResult]       = useState<QueryResponse | null>(null);
  const [error, setError]         = useState('');

  async function handleSearch() {
    if (!query.trim()) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await queryVet(query, {
        top_k: 8,
        filter_species: species !== 'All' ? species.toLowerCase() : undefined,
        filter_source:  source  !== 'All' ? source.toLowerCase()  : undefined,
      });
      setResult(res);
    } catch (err: any) {
      setError(err.message === 'offline'
        ? 'You are offline. Connect to search the knowledge base.'
        : 'Search failed. Try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <Text style={styles.title}>Search Manuals</Text>
        <Text style={styles.subtitle}>Search indexed veterinary references</Text>
      </View>

      <View style={styles.searchBox}>
        <TextInput
          style={styles.input}
          placeholder="e.g. bovine respiratory disease treatment"
          placeholderTextColor={Colors.textMuted}
          value={query}
          onChangeText={setQuery}
          returnKeyType="search"
          onSubmitEditing={handleSearch}
        />
        <TouchableOpacity
          style={[styles.searchBtn, loading && { opacity: 0.6 }]}
          onPress={handleSearch}
          disabled={loading}
        >
          {loading
            ? <ActivityIndicator size="small" color="#fff" />
            : <Text style={styles.searchBtnText}>Search</Text>
          }
        </TouchableOpacity>
      </View>

      {/* Species filter chips */}
      <FlatList
        horizontal
        data={SPECIES_FILTERS}
        keyExtractor={(i) => i}
        contentContainerStyle={styles.filterRow}
        showsHorizontalScrollIndicator={false}
        renderItem={({ item }) => (
          <TouchableOpacity
            style={[styles.chip, species === item && styles.chipActive]}
            onPress={() => setSpecies(item)}
          >
            <Text style={[styles.chipText, species === item && styles.chipTextActive]}>
              {item}
            </Text>
          </TouchableOpacity>
        )}
      />

      {/* Source filter chips */}
      <FlatList
        horizontal
        data={SOURCE_FILTERS}
        keyExtractor={(i) => i}
        contentContainerStyle={styles.filterRow}
        showsHorizontalScrollIndicator={false}
        renderItem={({ item }) => (
          <TouchableOpacity
            style={[styles.chip, styles.chipSource, source === item && styles.chipActive]}
            onPress={() => setSource(item)}
          >
            <Text style={[styles.chipText, source === item && styles.chipTextActive]}>
              {item}
            </Text>
          </TouchableOpacity>
        )}
      />

      {/* Error */}
      {!!error && (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      {/* Results */}
      {result && (
        <FlatList
          data={result.citations}
          keyExtractor={(_, i) => i.toString()}
          contentContainerStyle={styles.results}
          ListHeaderComponent={
            <View style={styles.answerBox}>
              <Text style={styles.answerLabel}>AI Summary</Text>
              <Text style={styles.answerText}>{result.answer}</Text>
              <Text style={styles.meta}>
                {result.chunks_retrieved} chunks · {result.latency_ms}ms · {result.llm_model}
              </Text>
            </View>
          }
          renderItem={({ item, index }) => (
            <View style={styles.citationCard}>
              <View style={styles.citationHeader}>
                <Text style={styles.citationRank}>#{index + 1}</Text>
                <Text style={styles.citationScore}>{Math.round(item.score * 100)}% match</Text>
              </View>
              <Text style={styles.citationTitle}>{item.document_title}</Text>
              <Text style={styles.citationPage}>Page {item.page_number}</Text>
              <Text style={styles.citationExcerpt} numberOfLines={4}>{item.excerpt}</Text>
            </View>
          )}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary,
    padding: Spacing.md,
    paddingTop: Spacing.lg,
  },
  title: { ...Typography.h3, color: '#fff' },
  subtitle: { ...Typography.caption, color: 'rgba(255,255,255,0.75)', marginTop: 2 },

  searchBox: {
    flexDirection: 'row',
    gap: Spacing.sm,
    padding: Spacing.md,
    backgroundColor: Colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: 10,
    ...Typography.body,
    color: Colors.textPrimary,
    backgroundColor: Colors.background,
  },
  searchBtn: {
    backgroundColor: Colors.primary,
    borderRadius: Radius.md,
    paddingHorizontal: Spacing.md,
    justifyContent: 'center',
  },
  searchBtnText: { ...Typography.label, color: '#fff' },

  filterRow: { paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm, gap: Spacing.sm },
  chip: {
    borderRadius: Radius.full,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingHorizontal: Spacing.md,
    paddingVertical: 5,
    backgroundColor: Colors.surface,
  },
  chipSource: { borderColor: Colors.accent },
  chipActive: { backgroundColor: Colors.primary, borderColor: Colors.primary },
  chipText: { ...Typography.label, color: Colors.textSecondary },
  chipTextActive: { color: '#fff' },

  errorBox: {
    margin: Spacing.md,
    padding: Spacing.md,
    backgroundColor: '#FEE',
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.error,
  },
  errorText: { ...Typography.body, color: Colors.error },

  results: { padding: Spacing.md, gap: Spacing.md },

  answerBox: {
    backgroundColor: Colors.surface,
    borderRadius: Radius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.md,
    borderLeftWidth: 4,
    borderLeftColor: Colors.primary,
    ...Shadow.sm,
  },
  answerLabel: { ...Typography.label, color: Colors.primary, marginBottom: Spacing.xs },
  answerText: { ...Typography.body, color: Colors.textPrimary },
  meta: { ...Typography.caption, color: Colors.textMuted, marginTop: Spacing.sm },

  citationCard: {
    backgroundColor: Colors.surface,
    borderRadius: Radius.lg,
    padding: Spacing.md,
    ...Shadow.sm,
  },
  citationHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  citationRank: { ...Typography.label, color: Colors.textMuted },
  citationScore: { ...Typography.label, color: Colors.primary },
  citationTitle: { ...Typography.h4, color: Colors.textPrimary },
  citationPage: { ...Typography.caption, color: Colors.textMuted, marginTop: 2 },
  citationExcerpt: { ...Typography.bodySmall, color: Colors.textSecondary, marginTop: Spacing.sm },
});

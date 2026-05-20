/**
 * vetgpt-mobile/app/(tabs)/schedule.tsx
 *
 * Schedule & Reminders screen.
 *
 * Features:
 *   - Create schedules from natural language ("I bought chicks today")
 *   - Create from template (chick vaccination, cattle heat, deworming)
 *   - View upcoming events with countdown
 *   - Mark events complete
 *   - Register device for push notifications
 *   - Choose reminder timing (1 day before, 3 days before, etc.)
 *   - Choose notification channels (push, Telegram, WhatsApp)
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  StyleSheet, SafeAreaView, ScrollView, Alert,
  ActivityIndicator, Switch, Platform,
} from 'react-native';
import * as Notifications from 'expo-notifications';
import { useAuthStore } from '../../store';
import { BASE_URL } from '../lib/api';
import { getItem } from '../lib/storage';
import { Colors, Spacing, Radius, Typography, Shadow } from '../../constants/theme';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ScheduleEvent {
  id:               string;
  schedule_name:    string;
  template_key:     string;
  species:          string;
  title:            string;
  description:      string;
  event_date:       string;
  is_critical:      boolean;
  reminder_days:    number[];
  notify_channels:  string[];
  status:           string;
  completed:        boolean;
  days_until:       number;
}

interface Template {
  key:         string;
  name:        string;
  species:     string;
  description: string;
  event_count: number;
}

type Screen = 'list' | 'create_nl' | 'create_template' | 'event_detail';

const SPECIES_EMOJI: Record<string, string> = {
  poultry: '🐔', cattle: '🐄', ovine_caprine: '🐐',
  pig: '🐷', dog: '🐕', cat: '🐈', horse: '🐴', custom: '📋',
};

const CHANNEL_LABELS: Record<string, string> = {
  push: '📱 Push', telegram: '✈️ Telegram', whatsapp: '💬 WhatsApp',
};

// ─── API helpers ──────────────────────────────────────────────────────────────

async function apiFetch(path: string, opts: RequestInit = {}): Promise<any> {
  const token = await getItem('vetgpt_auth_token');
  const res   = await fetch(`${BASE_URL}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers ?? {}),
    },
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error((d as any).detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ─── Push notification setup ──────────────────────────────────────────────────

async function registerForPushNotifications(): Promise<string | null> {
  try {
    const { status: existing } = await Notifications.getPermissionsAsync();
    let finalStatus = existing;

    if (existing !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }

    if (finalStatus !== 'granted') return null;

    const tokenData = await Notifications.getExpoPushTokenAsync();
    const token     = tokenData.data;

    // Register with backend
    await apiFetch('/api/schedules/push-token', {
      method: 'POST',
      body:   JSON.stringify({
        token,
        platform:    Platform.OS,
        device_name: `${Platform.OS} device`,
      }),
    });

    return token;
  } catch (err) {
    console.warn('Push registration failed:', err);
    return null;
  }
}

// ─── Sub-screens ──────────────────────────────────────────────────────────────

function EventList({
  onAdd, onSelect, onAddTemplate,
}: {
  onAdd: () => void;
  onSelect: (e: ScheduleEvent) => void;
  onAddTemplate: () => void;
}) {
  const [events, setEvents]         = useState<ScheduleEvent[]>([]);
  const [overdue, setOverdue]       = useState<ScheduleEvent[]>([]);
  const [loading, setLoading]       = useState(true);
  const [pushEnabled, setPushEnabled] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await apiFetch('/api/schedules/today');
      setEvents(data.today   ?? []);
      setOverdue(data.overdue ?? []);
    } catch {}
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    load();
    // Register push notifications
    registerForPushNotifications().then(token => setPushEnabled(!!token));

    // Set notification handler
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowAlert: true,
        shouldPlaySound: true,
        shouldSetBadge:  true,
      }),
    });
  }, []);

  async function markComplete(event: ScheduleEvent) {
    try {
      await apiFetch(`/api/schedules/${event.id}/complete`, {
        method: 'POST',
        body:   JSON.stringify({ notes: '' }),
      });
      load();
    } catch (err: any) {
      Alert.alert('Error', err.message);
    }
  }

  function renderEvent(item: ScheduleEvent, isOverdue = false) {
    const emoji     = SPECIES_EMOJI[item.species] ?? '📋';
    const daysLabel = item.days_until === 0
      ? 'TODAY'
      : item.days_until < 0
        ? `${Math.abs(item.days_until)}d overdue`
        : `in ${item.days_until}d`;

    return (
      <TouchableOpacity
        key={item.id}
        style={[s.eventCard, item.is_critical && s.eventCritical, isOverdue && s.eventOverdue]}
        onPress={() => onSelect(item)}
        activeOpacity={0.8}
      >
        <View style={s.eventLeft}>
          <Text style={s.eventEmoji}>{emoji}</Text>
        </View>
        <View style={s.eventMid}>
          <Text style={s.eventTitle} numberOfLines={2}>{item.title}</Text>
          <Text style={s.eventSched}>{item.schedule_name}</Text>
          <Text style={s.eventDate}>{new Date(item.event_date).toLocaleDateString()}</Text>
        </View>
        <View style={s.eventRight}>
          <View style={[s.daysBadge, item.is_critical && s.daysBadgeCritical, isOverdue && s.daysBadgeOverdue]}>
            <Text style={s.daysBadgeText}>{daysLabel}</Text>
          </View>
          <TouchableOpacity
            style={s.doneBtn}
            onPress={() => Alert.alert('Mark done?', item.title, [
              { text: 'Cancel' },
              { text: 'Mark done', onPress: () => markComplete(item) },
            ])}
          >
            <Text style={s.doneBtnText}>✓</Text>
          </TouchableOpacity>
        </View>
      </TouchableOpacity>
    );
  }

  if (loading) return <ActivityIndicator style={{ marginTop: 40 }} color={Colors.primary} />;

  return (
    <View style={{ flex: 1 }}>
      <ScrollView contentContainerStyle={s.list}>
        {!pushEnabled && (
          <TouchableOpacity
            style={s.pushBanner}
            onPress={() => registerForPushNotifications().then(t => setPushEnabled(!!t))}
          >
            <Text style={s.pushBannerText}>
              🔔 Enable push notifications to receive reminders
            </Text>
          </TouchableOpacity>
        )}

        {overdue.length > 0 && (
          <>
            <Text style={s.sectionHeader}>⚠️ Overdue</Text>
            {overdue.map(e => renderEvent(e, true))}
          </>
        )}

        {events.length > 0 && (
          <>
            <Text style={s.sectionHeader}>📅 Today</Text>
            {events.map(e => renderEvent(e))}
          </>
        )}

        {events.length === 0 && overdue.length === 0 && (
          <View style={s.empty}>
            <Text style={s.emptyEmoji}>📅</Text>
            <Text style={s.emptyTitle}>No events today</Text>
            <Text style={s.emptySub}>Create a schedule to get reminders</Text>
          </View>
        )}
      </ScrollView>

      {/* FABs */}
      <View style={s.fabGroup}>
        <TouchableOpacity style={[s.fab, s.fabSecondary]} onPress={onAddTemplate} activeOpacity={0.85}>
          <Text style={s.fabTextSecondary}>Templates</Text>
        </TouchableOpacity>
        <TouchableOpacity style={s.fab} onPress={onAdd} activeOpacity={0.85}>
          <Text style={s.fabText}>+ AI Schedule</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}


function CreateNLScreen({ onBack, onCreated }: { onBack: () => void; onCreated: () => void }) {
  const [text, setText]               = useState('');
  const [language, setLanguage]       = useState('en');
  const [reminderDays, setReminderDays] = useState([3, 1, 0]);
  const [channels, setChannels]       = useState(['push']);
  const [loading, setLoading]         = useState(false);
  const [result, setResult]           = useState<any>(null);

  const LANG_OPTIONS = [['en','English'],['sw','Kiswahili'],['fr','Français'],['ar','العربية']];
  const REMINDER_OPTIONS = [
    { label: 'Same day', value: 0 },
    { label: '1 day before', value: 1 },
    { label: '3 days before', value: 3 },
    { label: '7 days before', value: 7 },
  ];

  function toggleChannel(ch: string) {
    setChannels(prev => prev.includes(ch) ? prev.filter(c => c !== ch) : [...prev, ch]);
  }

  function toggleReminder(day: number) {
    setReminderDays(prev => prev.includes(day) ? prev.filter(d => d !== day) : [...prev, day].sort((a,b)=>b-a));
  }

  async function generate() {
    if (!text.trim()) {
      Alert.alert('Required', 'Describe what you want to schedule.');
      return;
    }
    if (channels.length === 0) {
      Alert.alert('Required', 'Select at least one notification channel.');
      return;
    }
    setLoading(true);
    try {
      const data = await apiFetch('/api/schedules/generate', {
        method: 'POST',
        body:   JSON.stringify({
          text,
          language,
          reminder_days:   reminderDays,
          notify_channels: channels,
        }),
      });
      setResult(data);
    } catch (err: any) {
      Alert.alert('Failed', err.message ?? 'Could not generate schedule. Try being more specific.');
    } finally {
      setLoading(false);
    }
  }

  if (result) {
    return (
      <ScrollView contentContainerStyle={s.form}>
        <View style={s.resultHeader}>
          <Text style={s.resultTitle}>✅ Schedule Created</Text>
          <Text style={s.resultName}>{result.schedule_name}</Text>
          <Text style={s.resultCount}>{result.events_created} reminders scheduled</Text>
        </View>
        {result.events?.slice(0, 5).map((ev: any) => (
          <View key={ev.id} style={s.resultEvent}>
            <Text style={s.resultEventDate}>{new Date(ev.event_date).toLocaleDateString()}</Text>
            <Text style={s.resultEventTitle}>{ev.title}</Text>
          </View>
        ))}
        {result.events?.length > 5 && (
          <Text style={s.resultMore}>+{result.events.length - 5} more events...</Text>
        )}
        <TouchableOpacity style={s.saveBtn} onPress={onCreated}>
          <Text style={s.saveBtnText}>View All Schedules</Text>
        </TouchableOpacity>
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={s.form} keyboardShouldPersistTaps="handled">
      <TouchableOpacity onPress={onBack} style={s.backBtn}>
        <Text style={s.backBtnText}>← Back</Text>
      </TouchableOpacity>
      <Text style={s.formTitle}>AI Schedule Generator</Text>
      <Text style={s.formSub}>
        Describe in your own words — the AI creates the full schedule.
      </Text>

      <View style={s.examplesBox}>
        <Text style={s.examplesTitle}>Examples:</Text>
        {[
          'I bought 200 chicks today',
          'My cow was served yesterday',
          'Start deworming my cattle herd next Monday',
          'Nilinanua vifaranga 100 leo',
        ].map(ex => (
          <TouchableOpacity key={ex} onPress={() => setText(ex)} style={s.exampleChip}>
            <Text style={s.exampleText}>{ex}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={s.label}>Your message</Text>
      <TextInput
        style={[s.input, { minHeight: 80 }]}
        value={text}
        onChangeText={setText}
        multiline
        placeholder="Describe what happened or what you want to schedule..."
        placeholderTextColor={Colors.textMuted}
      />

      <Text style={s.label}>Language</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: Spacing.md }}>
        {LANG_OPTIONS.map(([code, label]) => (
          <TouchableOpacity
            key={code}
            style={[s.chip, language === code && s.chipActive]}
            onPress={() => setLanguage(code)}
          >
            <Text style={[s.chipText, language === code && s.chipTextActive]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <Text style={s.label}>Remind me</Text>
      <View style={s.reminderGrid}>
        {REMINDER_OPTIONS.map(({ label, value }) => (
          <TouchableOpacity
            key={value}
            style={[s.reminderChip, reminderDays.includes(value) && s.chipActive]}
            onPress={() => toggleReminder(value)}
          >
            <Text style={[s.chipText, reminderDays.includes(value) && s.chipTextActive]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={s.label}>Notify via</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm, marginBottom: Spacing.md }}>
        {Object.entries(CHANNEL_LABELS).map(([key, label]) => (
          <TouchableOpacity
            key={key}
            style={[s.chip, channels.includes(key) && s.chipActive]}
            onPress={() => toggleChannel(key)}
          >
            <Text style={[s.chipText, channels.includes(key) && s.chipTextActive]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity
        style={[s.saveBtn, loading && { opacity: 0.6 }]}
        onPress={generate}
        disabled={loading}
        activeOpacity={0.85}
      >
        {loading
          ? <><ActivityIndicator color="#fff" /><Text style={[s.saveBtnText, { marginLeft: 8 }]}>Generating...</Text></>
          : <Text style={s.saveBtnText}>🤖 Generate Schedule</Text>
        }
      </TouchableOpacity>
    </ScrollView>
  );
}


function TemplateScreen({ onBack, onCreated }: { onBack: () => void; onCreated: () => void }) {
  const [templates, setTemplates]   = useState<Template[]>([]);
  const [selected, setSelected]     = useState<Template | null>(null);
  const [scheduleName, setScheduleName] = useState('');
  const [startDate, setStartDate]   = useState(new Date().toISOString().split('T')[0]);
  const [reminderDays, setReminderDays] = useState([3, 1, 0]);
  const [channels, setChannels]     = useState(['push']);
  const [loading, setLoading]       = useState(false);

  useEffect(() => {
    apiFetch('/api/schedules/templates').then(setTemplates).catch(() => {});
  }, []);

  function toggleChannel(ch: string) {
    setChannels(prev => prev.includes(ch) ? prev.filter(c => c !== ch) : [...prev, ch]);
  }

  async function create() {
    if (!selected) { Alert.alert('Select a template'); return; }
    if (!scheduleName.trim()) { Alert.alert('Required', 'Enter a schedule name.'); return; }
    setLoading(true);
    try {
      await apiFetch('/api/schedules/from-template', {
        method: 'POST',
        body: JSON.stringify({
          template_key:    selected.key,
          start_date:      startDate,
          schedule_name:   scheduleName,
          reminder_days:   reminderDays,
          notify_channels: channels,
        }),
      });
      Alert.alert('Created!', `${selected.name} schedule created successfully.`, [
        { text: 'OK', onPress: onCreated }
      ]);
    } catch (err: any) {
      Alert.alert('Error', err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={s.form} keyboardShouldPersistTaps="handled">
      <TouchableOpacity onPress={onBack} style={s.backBtn}>
        <Text style={s.backBtnText}>← Back</Text>
      </TouchableOpacity>
      <Text style={s.formTitle}>From Template</Text>

      <Text style={s.label}>Select template</Text>
      {templates.map(t => (
        <TouchableOpacity
          key={t.key}
          style={[s.templateCard, selected?.key === t.key && s.templateCardActive]}
          onPress={() => { setSelected(t); setScheduleName(t.name); }}
        >
          <Text style={s.templateEmoji}>{SPECIES_EMOJI[t.species] ?? '📋'}</Text>
          <View style={{ flex: 1 }}>
            <Text style={s.templateName}>{t.name}</Text>
            <Text style={s.templateDesc}>{t.description}</Text>
            <Text style={s.templateCount}>{t.event_count} scheduled events</Text>
          </View>
          {selected?.key === t.key && <Text style={{ color: Colors.primary, fontSize: 20 }}>✓</Text>}
        </TouchableOpacity>
      ))}

      {selected && (
        <>
          <Text style={s.label}>Schedule name</Text>
          <TextInput
            style={s.input}
            value={scheduleName}
            onChangeText={setScheduleName}
            placeholder="e.g. Batch A — June 2025"
            placeholderTextColor={Colors.textMuted}
          />

          <Text style={s.label}>Start date</Text>
          <TextInput
            style={s.input}
            value={startDate}
            onChangeText={setStartDate}
            placeholder="YYYY-MM-DD"
            placeholderTextColor={Colors.textMuted}
          />

          <Text style={s.label}>Notify via</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm, marginBottom: Spacing.md }}>
            {Object.entries(CHANNEL_LABELS).map(([key, label]) => (
              <TouchableOpacity
                key={key}
                style={[s.chip, channels.includes(key) && s.chipActive]}
                onPress={() => toggleChannel(key)}
              >
                <Text style={[s.chipText, channels.includes(key) && s.chipTextActive]}>{label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <TouchableOpacity
            style={[s.saveBtn, loading && { opacity: 0.6 }]}
            onPress={create}
            disabled={loading}
          >
            {loading
              ? <ActivityIndicator color="#fff" />
              : <Text style={s.saveBtnText}>Create Schedule</Text>
            }
          </TouchableOpacity>
        </>
      )}
    </ScrollView>
  );
}


function EventDetail({ event, onBack, onUpdated }: {
  event: ScheduleEvent; onBack: () => void; onUpdated: () => void;
}) {
  const [completing, setCompleting] = useState(false);
  const [notes, setNotes]           = useState('');

  async function complete() {
    setCompleting(true);
    try {
      await apiFetch(`/api/schedules/${event.id}/complete`, {
        method: 'POST',
        body:   JSON.stringify({ notes }),
      });
      onUpdated();
    } catch (err: any) {
      Alert.alert('Error', err.message);
    } finally {
      setCompleting(false);
    }
  }

  const daysLabel = event.days_until === 0
    ? '📅 TODAY'
    : event.days_until < 0
      ? `⚠️ ${Math.abs(event.days_until)} days overdue`
      : `🔔 In ${event.days_until} days`;

  return (
    <ScrollView contentContainerStyle={s.form}>
      <TouchableOpacity onPress={onBack} style={s.backBtn}>
        <Text style={s.backBtnText}>← Back</Text>
      </TouchableOpacity>

      <View style={[s.detailHero, event.is_critical && { backgroundColor: Colors.error + '15' }]}>
        <Text style={s.detailDays}>{daysLabel}</Text>
        <Text style={s.detailTitle}>{event.title}</Text>
        <Text style={s.detailSched}>{event.schedule_name}</Text>
        <Text style={s.detailDate}>{new Date(event.event_date).toLocaleDateString('en-GB', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</Text>
      </View>

      {!!event.description && (
        <View style={s.detailDesc}>
          <Text style={s.detailDescTitle}>What to do:</Text>
          <Text style={s.detailDescText}>{event.description}</Text>
        </View>
      )}

      <View style={s.detailMeta}>
        <Text style={s.detailMetaRow}>🔔 Reminders: {event.reminder_days.map(d => d === 0 ? 'Same day' : `${d}d before`).join(', ')}</Text>
        <Text style={s.detailMetaRow}>📲 Channels: {event.notify_channels.map(c => CHANNEL_LABELS[c] ?? c).join(', ')}</Text>
        {event.is_critical && <Text style={[s.detailMetaRow, { color: Colors.error }]}>🚨 Critical event</Text>}
      </View>

      {!event.completed && (
        <>
          <Text style={s.label}>Completion notes (optional)</Text>
          <TextInput
            style={[s.input, { minHeight: 60 }]}
            value={notes}
            onChangeText={setNotes}
            multiline
            placeholder="e.g. Vaccine administered, 200 birds treated"
            placeholderTextColor={Colors.textMuted}
          />
          <TouchableOpacity
            style={[s.saveBtn, completing && { opacity: 0.6 }]}
            onPress={complete}
            disabled={completing}
          >
            {completing ? <ActivityIndicator color="#fff" /> : <Text style={s.saveBtnText}>✓ Mark Complete</Text>}
          </TouchableOpacity>
        </>
      )}

      {event.completed && (
        <View style={s.completedBadge}>
          <Text style={s.completedText}>✅ Completed</Text>
        </View>
      )}
    </ScrollView>
  );
}


// ─── Main screen ──────────────────────────────────────────────────────────────

export default function ScheduleScreen() {
  const [screen, setScreen]         = useState<Screen>('list');
  const [selectedEvent, setSelectedEvent] = useState<ScheduleEvent | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  function refresh() { setRefreshKey(k => k + 1); setScreen('list'); }

  return (
    <SafeAreaView style={s.safe}>
      <View style={s.header}>
        <Text style={s.headerTitle}>Schedules & Reminders</Text>
        <Text style={s.headerSub}>Vaccination, heat cycles, treatments</Text>
      </View>

      {screen === 'list' && (
        <EventList
          key={refreshKey}
          onAdd={() => setScreen('create_nl')}
          onAddTemplate={() => setScreen('create_template')}
          onSelect={e => { setSelectedEvent(e); setScreen('event_detail'); }}
        />
      )}
      {screen === 'create_nl' && (
        <CreateNLScreen onBack={() => setScreen('list')} onCreated={refresh} />
      )}
      {screen === 'create_template' && (
        <TemplateScreen onBack={() => setScreen('list')} onCreated={refresh} />
      )}
      {screen === 'event_detail' && selectedEvent && (
        <EventDetail event={selectedEvent} onBack={() => setScreen('list')} onUpdated={refresh} />
      )}
    </SafeAreaView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: Colors.background },
  header: { backgroundColor: Colors.primary, paddingHorizontal: Spacing.md, paddingTop: Spacing.lg, paddingBottom: Spacing.md },
  headerTitle: { ...Typography.h3, color: '#fff' },
  headerSub:   { ...Typography.caption, color: 'rgba(255,255,255,0.75)', marginTop: 2 },

  list:   { padding: Spacing.md, paddingBottom: 120 },
  sectionHeader: { ...Typography.label, color: Colors.textMuted, marginTop: Spacing.md, marginBottom: Spacing.sm },

  eventCard:     { backgroundColor: Colors.surface, borderRadius: Radius.lg, padding: Spacing.md, marginBottom: Spacing.sm, flexDirection: 'row', alignItems: 'center', ...Shadow.sm },
  eventCritical: { borderLeftWidth: 4, borderLeftColor: Colors.error },
  eventOverdue:  { backgroundColor: '#FFF3CD' },
  eventLeft:     { marginRight: Spacing.sm },
  eventEmoji:    { fontSize: 28 },
  eventMid:      { flex: 1 },
  eventTitle:    { ...Typography.h4, color: Colors.textPrimary },
  eventSched:    { ...Typography.caption, color: Colors.textMuted },
  eventDate:     { ...Typography.caption, color: Colors.textSecondary },
  eventRight:    { alignItems: 'flex-end', gap: 6 },
  daysBadge:     { backgroundColor: Colors.primary + '20', borderRadius: Radius.full, paddingHorizontal: 8, paddingVertical: 3 },
  daysBadgeCritical: { backgroundColor: Colors.error + '20' },
  daysBadgeOverdue:  { backgroundColor: '#FFC107' + '40' },
  daysBadgeText: { ...Typography.caption, color: Colors.primary, fontWeight: '700' },
  doneBtn:       { backgroundColor: Colors.success + '20', borderRadius: Radius.full, width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  doneBtnText:   { color: Colors.success, fontWeight: '700', fontSize: 16 },

  empty:       { alignItems: 'center', paddingTop: 80 },
  emptyEmoji:  { fontSize: 48, marginBottom: Spacing.md },
  emptyTitle:  { ...Typography.h3, color: Colors.textPrimary },
  emptySub:    { ...Typography.body, color: Colors.textMuted, textAlign: 'center', marginTop: 4 },

  pushBanner:     { backgroundColor: Colors.primary + '15', borderRadius: Radius.md, padding: Spacing.md, marginBottom: Spacing.md, borderWidth: 1, borderColor: Colors.primary + '30' },
  pushBannerText: { ...Typography.body, color: Colors.primary, textAlign: 'center' },

  fabGroup:     { position: 'absolute', bottom: 24, right: 16, flexDirection: 'row', gap: Spacing.sm },
  fab:          { backgroundColor: Colors.primary, borderRadius: Radius.full, paddingHorizontal: Spacing.lg, paddingVertical: 14, ...Shadow.lg },
  fabSecondary: { backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.primary },
  fabText:      { ...Typography.h4, color: '#fff' },
  fabTextSecondary: { ...Typography.h4, color: Colors.primary },

  form:        { padding: Spacing.lg, paddingBottom: 60 },
  formTitle:   { ...Typography.h2, color: Colors.textPrimary, marginBottom: Spacing.xs },
  formSub:     { ...Typography.body, color: Colors.textMuted, marginBottom: Spacing.lg },
  backBtn:     { marginBottom: Spacing.md },
  backBtnText: { ...Typography.body, color: Colors.primary },
  label:       { ...Typography.label, color: Colors.textSecondary, marginBottom: 6 },
  input:       { borderWidth: 1, borderColor: Colors.border, borderRadius: Radius.md, paddingHorizontal: Spacing.md, paddingVertical: 11, ...Typography.body, color: Colors.textPrimary, marginBottom: Spacing.md, backgroundColor: Colors.surface },
  saveBtn:     { backgroundColor: Colors.primary, borderRadius: Radius.md, paddingVertical: 15, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', marginTop: Spacing.sm },
  saveBtnText: { ...Typography.h4, color: '#fff' },

  chip:          { borderRadius: Radius.full, borderWidth: 1, borderColor: Colors.border, paddingHorizontal: Spacing.md, paddingVertical: 6, marginRight: Spacing.sm, backgroundColor: Colors.surface },
  chipActive:    { backgroundColor: Colors.primary, borderColor: Colors.primary },
  chipText:      { ...Typography.caption, color: Colors.textSecondary },
  chipTextActive:{ color: '#fff' },

  examplesBox:   { backgroundColor: Colors.surfaceAlt, borderRadius: Radius.lg, padding: Spacing.md, marginBottom: Spacing.md },
  examplesTitle: { ...Typography.label, color: Colors.textMuted, marginBottom: Spacing.sm },
  exampleChip:   { backgroundColor: Colors.surface, borderRadius: Radius.md, padding: Spacing.sm, marginBottom: 6, borderWidth: 1, borderColor: Colors.border },
  exampleText:   { ...Typography.body, color: Colors.primary },

  reminderGrid:  { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.sm, marginBottom: Spacing.md },
  reminderChip:  { borderRadius: Radius.md, borderWidth: 1, borderColor: Colors.border, paddingHorizontal: Spacing.md, paddingVertical: 8, backgroundColor: Colors.surface },

  templateCard:       { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surface, borderRadius: Radius.lg, padding: Spacing.md, marginBottom: Spacing.sm, borderWidth: 1, borderColor: Colors.border, ...Shadow.sm, gap: Spacing.sm },
  templateCardActive: { borderColor: Colors.primary, backgroundColor: Colors.primary + '08' },
  templateEmoji:      { fontSize: 32 },
  templateName:       { ...Typography.h4, color: Colors.textPrimary },
  templateDesc:       { ...Typography.caption, color: Colors.textMuted, marginTop: 2 },
  templateCount:      { ...Typography.caption, color: Colors.primary, marginTop: 2 },

  resultHeader:     { backgroundColor: Colors.success + '15', borderRadius: Radius.lg, padding: Spacing.lg, marginBottom: Spacing.md, alignItems: 'center' },
  resultTitle:      { ...Typography.h3, color: Colors.success },
  resultName:       { ...Typography.h4, color: Colors.textPrimary, marginTop: 4 },
  resultCount:      { ...Typography.body, color: Colors.textMuted, marginTop: 4 },
  resultEvent:      { flexDirection: 'row', gap: Spacing.md, paddingVertical: Spacing.sm, borderBottomWidth: 1, borderBottomColor: Colors.border },
  resultEventDate:  { ...Typography.caption, color: Colors.textMuted, width: 80 },
  resultEventTitle: { ...Typography.body, color: Colors.textPrimary, flex: 1 },
  resultMore:       { ...Typography.caption, color: Colors.textMuted, textAlign: 'center', marginTop: Spacing.sm },

  detailHero:     { backgroundColor: Colors.primary + '10', borderRadius: Radius.xl, padding: Spacing.lg, marginBottom: Spacing.md },
  detailDays:     { ...Typography.h4, color: Colors.primary, marginBottom: 4 },
  detailTitle:    { ...Typography.h2, color: Colors.textPrimary },
  detailSched:    { ...Typography.caption, color: Colors.textMuted, marginTop: 4 },
  detailDate:     { ...Typography.body, color: Colors.textSecondary, marginTop: 4 },
  detailDesc:     { backgroundColor: Colors.surface, borderRadius: Radius.lg, padding: Spacing.md, marginBottom: Spacing.md, borderWidth: 1, borderColor: Colors.border },
  detailDescTitle:{ ...Typography.label, color: Colors.textMuted, marginBottom: 6 },
  detailDescText: { ...Typography.body, color: Colors.textPrimary },
  detailMeta:     { marginBottom: Spacing.md },
  detailMetaRow:  { ...Typography.body, color: Colors.textSecondary, marginBottom: 4 },

  completedBadge: { backgroundColor: Colors.success + '15', borderRadius: Radius.lg, padding: Spacing.lg, alignItems: 'center' },
  completedText:  { ...Typography.h3, color: Colors.success },
});

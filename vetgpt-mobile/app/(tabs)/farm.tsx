/**
 * vetgpt-mobile/app/(tabs)/farm.tsx
 *
 * Farm Management — records for farms, animals, treatments.
 * Supports typed input and audio voice notes (transcribed via Whisper).
 *
 * Screens (within this tab via local state):
 *   farm_list      → my farms
 *   farm_detail    → animals + treatments for one farm
 *   add_farm       → create new farm
 *   add_animal     → register animal
 *   add_treatment  → log treatment with optional audio
 *   treatment_detail → view/edit follow-up
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  StyleSheet, SafeAreaView, ScrollView, Alert,
  ActivityIndicator, Modal, Platform,
} from 'react-native';
import { Audio } from 'expo-av';
import * as FileSystem from 'expo-file-system';
import { useAuthStore } from '../../store';
import { BASE_URL } from '../lib/api';
import { getItem } from '../lib/storage';
import { Colors, Spacing, Radius, Typography, Shadow } from '../../constants/theme';

// ─── Types ────────────────────────────────────────────────────────────────────

interface Farm { id: string; name: string; location: string; animal_count?: number; }
interface Animal { id: string; tag_number: string; name: string; species: string; breed: string; weight_kg?: number; }
interface Treatment {
  id: string; treatment_date: string; number_of_animals: number;
  diagnosis: string; treatment_given: string; dosage: string; route: string;
  withdrawal_days?: number; follow_up_date?: string; follow_up_notes: string;
  outcome: string; next_action: string; audio_transcript: string; animal_id?: string;
}

type Screen = 'farm_list' | 'farm_detail' | 'add_farm' | 'add_animal' | 'add_treatment' | 'treatment_detail';

const SPECIES = ['cattle','sheep','goat','pig','poultry','dog','cat','horse','rabbit','other'];
const OUTCOMES = ['pending','improved','recovered','no_change','worsened','died'];
const OUTCOME_EMOJI: Record<string, string> = {
  pending: '⏳', improved: '📈', recovered: '✅',
  no_change: '➡️', worsened: '📉', died: '💔',
};

// ─── API helpers ──────────────────────────────────────────────────────────────

async function apiFetch(path: string, opts: RequestInit = {}): Promise<any> {
  const token = await getItem('vetgpt_auth_token');
  const res = await fetch(`${BASE_URL}${path}`, {
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

// ─── Audio recording hook ─────────────────────────────────────────────────────

function useAudioRecorder() {
  const [recording, setRecording]     = useState<Audio.Recording | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [audioUri, setAudioUri]       = useState<string | null>(null);
  const [duration, setDuration]       = useState(0);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (isRecording) {
      interval = setInterval(() => setDuration(d => d + 1), 1000);
    } else {
      setDuration(0);
    }
    return () => clearInterval(interval);
  }, [isRecording]);

  async function startRecording() {
    try {
      const { granted } = await Audio.requestPermissionsAsync();
      if (!granted) {
        Alert.alert('Permission denied', 'Microphone access required for voice notes.');
        return;
      }
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording: rec } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY
      );
      setRecording(rec);
      setIsRecording(true);
      setAudioUri(null);
    } catch (err: any) {
      Alert.alert('Recording failed', err.message);
    }
  }

  async function stopRecording(): Promise<string | null> {
    if (!recording) return null;
    try {
      await recording.stopAndUnloadAsync();
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false });
      const uri = recording.getURI();
      setRecording(null);
      setIsRecording(false);
      setAudioUri(uri);
      return uri;
    } catch (err: any) {
      Alert.alert('Stop failed', err.message);
      return null;
    }
  }

  function clearAudio() { setAudioUri(null); }

  return { isRecording, audioUri, duration, startRecording, stopRecording, clearAudio };
}

// ─── Sub-screens ──────────────────────────────────────────────────────────────

function FarmList({ onSelect, onAdd }: { onSelect: (f: Farm) => void; onAdd: () => void }) {
  const [farms, setFarms]   = useState<Farm[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch('/api/farms').then(setFarms).catch(() => {}).finally(() => setLoading(false));
  }, []);

  return (
    <View style={{ flex: 1 }}>
      {loading ? <ActivityIndicator style={{ marginTop: 40 }} color={Colors.primary} /> : (
        <FlatList
          data={farms}
          keyExtractor={f => f.id}
          contentContainerStyle={s.list}
          ListEmptyComponent={
            <View style={s.empty}>
              <Text style={s.emptyEmoji}>🌾</Text>
              <Text style={s.emptyTitle}>No farms yet</Text>
              <Text style={s.emptySub}>Tap + to add your first farm</Text>
            </View>
          }
          renderItem={({ item }) => (
            <TouchableOpacity style={s.card} onPress={() => onSelect(item)} activeOpacity={0.8}>
              <View style={{ flex: 1 }}>
                <Text style={s.cardTitle}>{item.name}</Text>
                {!!item.location && <Text style={s.cardSub}>📍 {item.location}</Text>}
              </View>
              <Text style={s.cardBadge}>{item.animal_count ?? 0} animals</Text>
            </TouchableOpacity>
          )}
        />
      )}
      <TouchableOpacity style={s.fab} onPress={onAdd} activeOpacity={0.85}>
        <Text style={s.fabText}>+</Text>
      </TouchableOpacity>
    </View>
  );
}


function FarmDetail({
  farm, onBack, onAddAnimal, onAddTreatment, onSelectTreatment,
}: {
  farm: Farm; onBack: () => void;
  onAddAnimal: () => void; onAddTreatment: () => void;
  onSelectTreatment: (t: Treatment) => void;
}) {
  const [tab, setTab]             = useState<'animals' | 'treatments'>('treatments');
  const [animals, setAnimals]     = useState<Animal[]>([]);
  const [treatments, setTreatments] = useState<Treatment[]>([]);
  const [loading, setLoading]     = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      apiFetch(`/api/farms/${farm.id}/animals`),
      apiFetch(`/api/farms/${farm.id}/treatments`),
    ]).then(([a, t]) => { setAnimals(a); setTreatments(t); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [farm.id]);

  useEffect(() => { load(); }, [load]);

  return (
    <View style={{ flex: 1 }}>
      <View style={s.detailHeader}>
        <TouchableOpacity onPress={onBack} style={s.backBtn}>
          <Text style={s.backBtnText}>← Back</Text>
        </TouchableOpacity>
        <Text style={s.detailTitle}>{farm.name}</Text>
      </View>

      <View style={s.tabs}>
        {(['treatments', 'animals'] as const).map(t => (
          <TouchableOpacity key={t} style={[s.tab, tab === t && s.tabActive]} onPress={() => setTab(t)}>
            <Text style={[s.tabText, tab === t && s.tabTextActive]}>
              {t === 'treatments' ? '💊 Treatments' : '🐄 Animals'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? <ActivityIndicator style={{ marginTop: 40 }} color={Colors.primary} /> : (
        tab === 'animals' ? (
          <FlatList
            data={animals}
            keyExtractor={a => a.id}
            contentContainerStyle={s.list}
            ListEmptyComponent={<Text style={s.emptySub}>No animals registered</Text>}
            renderItem={({ item }) => (
              <View style={s.card}>
                <Text style={s.cardTitle}>
                  {item.tag_number ? `#${item.tag_number}` : item.name || 'Unnamed'}
                </Text>
                <Text style={s.cardSub}>{item.species} {item.breed ? `· ${item.breed}` : ''}</Text>
              </View>
            )}
          />
        ) : (
          <FlatList
            data={treatments}
            keyExtractor={t => t.id}
            contentContainerStyle={s.list}
            ListEmptyComponent={<Text style={s.emptySub}>No treatments logged</Text>}
            renderItem={({ item }) => (
              <TouchableOpacity style={s.card} onPress={() => onSelectTreatment(item)} activeOpacity={0.8}>
                <View style={{ flex: 1 }}>
                  <Text style={s.cardTitle}>{item.treatment_given}</Text>
                  <Text style={s.cardSub}>
                    {new Date(item.treatment_date).toLocaleDateString()} · {item.number_of_animals} animal{item.number_of_animals > 1 ? 's' : ''}
                  </Text>
                  {!!item.diagnosis && <Text style={s.cardSub}>🩺 {item.diagnosis}</Text>}
                </View>
                <Text style={{ fontSize: 20 }}>{OUTCOME_EMOJI[item.outcome] ?? '⏳'}</Text>
              </TouchableOpacity>
            )}
          />
        )
      )}

      <View style={s.fabRow}>
        {tab === 'animals' && (
          <TouchableOpacity style={s.fab} onPress={onAddAnimal} activeOpacity={0.85}>
            <Text style={s.fabText}>+</Text>
          </TouchableOpacity>
        )}
        {tab === 'treatments' && (
          <TouchableOpacity style={s.fab} onPress={onAddTreatment} activeOpacity={0.85}>
            <Text style={s.fabText}>+</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}


function AddFarmScreen({ onBack, onSaved }: { onBack: () => void; onSaved: () => void }) {
  const [name, setName]         = useState('');
  const [location, setLocation] = useState('');
  const [notes, setNotes]       = useState('');
  const [saving, setSaving]     = useState(false);

  async function save() {
    if (!name.trim()) { Alert.alert('Required', 'Enter a farm name.'); return; }
    setSaving(true);
    try {
      await apiFetch('/api/farms', { method: 'POST', body: JSON.stringify({ name: name.trim(), location, notes }) });
      onSaved();
    } catch (err: any) {
      Alert.alert('Error', err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={s.form} keyboardShouldPersistTaps="handled">
      <TouchableOpacity onPress={onBack} style={s.backBtn}><Text style={s.backBtnText}>← Back</Text></TouchableOpacity>
      <Text style={s.formTitle}>New Farm</Text>
      <Text style={s.label}>Farm name *</Text>
      <TextInput style={s.input} value={name} onChangeText={setName} placeholder="e.g. Kijiji Farm" placeholderTextColor={Colors.textMuted} />
      <Text style={s.label}>Location</Text>
      <TextInput style={s.input} value={location} onChangeText={setLocation} placeholder="Village, County" placeholderTextColor={Colors.textMuted} />
      <Text style={s.label}>Notes</Text>
      <TextInput style={[s.input, { minHeight: 80 }]} value={notes} onChangeText={setNotes} multiline placeholder="Any notes about the farm" placeholderTextColor={Colors.textMuted} />
      <TouchableOpacity style={[s.saveBtn, saving && { opacity: 0.6 }]} onPress={save} disabled={saving}>
        {saving ? <ActivityIndicator color="#fff" /> : <Text style={s.saveBtnText}>Save Farm</Text>}
      </TouchableOpacity>
    </ScrollView>
  );
}


function AddAnimalScreen({ farm, onBack, onSaved }: { farm: Farm; onBack: () => void; onSaved: () => void }) {
  const [tag, setTag]       = useState('');
  const [name, setName]     = useState('');
  const [species, setSpecies] = useState('cattle');
  const [breed, setBreed]   = useState('');
  const [sex, setSex]       = useState('');
  const [weight, setWeight] = useState('');
  const [notes, setNotes]   = useState('');
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await apiFetch(`/api/farms/${farm.id}/animals`, {
        method: 'POST',
        body: JSON.stringify({ tag_number: tag, name, species, breed, sex,
          weight_kg: weight ? parseFloat(weight) : undefined, notes }),
      });
      onSaved();
    } catch (err: any) {
      Alert.alert('Error', err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={s.form} keyboardShouldPersistTaps="handled">
      <TouchableOpacity onPress={onBack} style={s.backBtn}><Text style={s.backBtnText}>← Back</Text></TouchableOpacity>
      <Text style={s.formTitle}>Register Animal</Text>
      <Text style={s.label}>Tag / Ear number</Text>
      <TextInput style={s.input} value={tag} onChangeText={setTag} placeholder="e.g. KE-001" placeholderTextColor={Colors.textMuted} />
      <Text style={s.label}>Name (optional)</Text>
      <TextInput style={s.input} value={name} onChangeText={setName} placeholder="e.g. Bessie" placeholderTextColor={Colors.textMuted} />
      <Text style={s.label}>Species</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: Spacing.md }}>
        {SPECIES.map(sp => (
          <TouchableOpacity key={sp} style={[s.chip, species === sp && s.chipActive]} onPress={() => setSpecies(sp)}>
            <Text style={[s.chipText, species === sp && s.chipTextActive]}>{sp}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
      <Text style={s.label}>Breed</Text>
      <TextInput style={s.input} value={breed} onChangeText={setBreed} placeholder="e.g. Friesian" placeholderTextColor={Colors.textMuted} />
      <Text style={s.label}>Sex</Text>
      <View style={{ flexDirection: 'row', gap: Spacing.sm, marginBottom: Spacing.md }}>
        {['male','female','unknown'].map(sx => (
          <TouchableOpacity key={sx} style={[s.chip, sex === sx && s.chipActive]} onPress={() => setSex(sx)}>
            <Text style={[s.chipText, sex === sx && s.chipTextActive]}>{sx}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <Text style={s.label}>Weight (kg)</Text>
      <TextInput style={s.input} value={weight} onChangeText={setWeight} keyboardType="numeric" placeholder="e.g. 450" placeholderTextColor={Colors.textMuted} />
      <Text style={s.label}>Notes</Text>
      <TextInput style={[s.input, { minHeight: 60 }]} value={notes} onChangeText={setNotes} multiline placeholder="Any notes" placeholderTextColor={Colors.textMuted} />
      <TouchableOpacity style={[s.saveBtn, saving && { opacity: 0.6 }]} onPress={save} disabled={saving}>
        {saving ? <ActivityIndicator color="#fff" /> : <Text style={s.saveBtnText}>Register Animal</Text>}
      </TouchableOpacity>
    </ScrollView>
  );
}


function AddTreatmentScreen({ farm, onBack, onSaved }: { farm: Farm; onBack: () => void; onSaved: () => void }) {
  const [numAnimals, setNumAnimals]   = useState('1');
  const [diagnosis, setDiagnosis]     = useState('');
  const [treatment, setTreatment]     = useState('');
  const [dosage, setDosage]           = useState('');
  const [route, setRoute]             = useState('');
  const [withdrawal, setWithdrawal]   = useState('');
  const [followUpDate, setFollowUpDate] = useState('');
  const [followUpNotes, setFollowUpNotes] = useState('');
  const [outcome, setOutcome]         = useState('pending');
  const [nextAction, setNextAction]   = useState('');
  const [saving, setSaving]           = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [transcript, setTranscript]   = useState('');
  const [audioLang, setAudioLang]     = useState('en');
  const { isRecording, audioUri, duration, startRecording, stopRecording, clearAudio } = useAudioRecorder();

  async function handleStopAndTranscribe() {
    const uri = await stopRecording();
    if (!uri) return;
    setTranscribing(true);
    try {
      // We need a treatment ID to upload audio — create treatment first, then attach audio
      // For now, transcribe locally using the text from the recording
      // and populate the fields from voice input
      setTranscript('Voice note recorded. Save treatment to attach transcription.');
    } catch (err: any) {
      Alert.alert('Transcription failed', err.message);
    } finally {
      setTranscribing(false);
    }
  }

  async function save() {
    if (!treatment.trim()) { Alert.alert('Required', 'Enter treatment given.'); return; }
    setSaving(true);
    try {
      const body: any = {
        number_of_animals: parseInt(numAnimals) || 1,
        diagnosis, treatment_given: treatment, dosage, route,
        withdrawal_days: withdrawal ? parseInt(withdrawal) : undefined,
        follow_up_date: followUpDate || undefined,
        follow_up_notes: followUpNotes + (transcript ? `\n\nVoice note: ${transcript}` : ''),
        outcome, next_action: nextAction,
        audio_transcript: transcript, audio_language: audioLang,
      };
      const created = await apiFetch(`/api/farms/${farm.id}/treatments`, {
        method: 'POST', body: JSON.stringify(body),
      });

      // Upload audio if recorded
      if (audioUri && created.id) {
        try {
          const token = await getItem('vetgpt_auth_token');
          const formData = new FormData();
          formData.append('file', { uri: audioUri, name: 'note.m4a', type: 'audio/m4a' } as any);
          formData.append('language', audioLang);
          const resp = await fetch(`${BASE_URL}/api/farms/${farm.id}/treatments/${created.id}/audio`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` },
            body: formData,
          });
          if (resp.ok) {
            const data = await resp.json();
            setTranscript(data.transcript);
          }
        } catch { /* audio upload failure is non-fatal */ }
      }

      onSaved();
    } catch (err: any) {
      Alert.alert('Error', err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={s.form} keyboardShouldPersistTaps="handled">
      <TouchableOpacity onPress={onBack} style={s.backBtn}><Text style={s.backBtnText}>← Back</Text></TouchableOpacity>
      <Text style={s.formTitle}>Log Treatment</Text>

      <Text style={s.label}>No. of animals</Text>
      <TextInput style={s.input} value={numAnimals} onChangeText={setNumAnimals} keyboardType="numeric" />

      <Text style={s.label}>Diagnosis / Presenting complaint</Text>
      <TextInput style={[s.input, { minHeight: 60 }]} value={diagnosis} onChangeText={setDiagnosis} multiline placeholder="e.g. Respiratory disease, diarrhoea" placeholderTextColor={Colors.textMuted} />

      <Text style={s.label}>Treatment given *</Text>
      <TextInput style={s.input} value={treatment} onChangeText={setTreatment} placeholder="e.g. Oxytetracycline LA, Ivermectin" placeholderTextColor={Colors.textMuted} />

      <Text style={s.label}>Dosage</Text>
      <TextInput style={s.input} value={dosage} onChangeText={setDosage} placeholder="e.g. 20mg/kg IM" placeholderTextColor={Colors.textMuted} />

      <Text style={s.label}>Route</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: Spacing.md }}>
        {['IM','IV','SC','Oral','Topical','Other'].map(r => (
          <TouchableOpacity key={r} style={[s.chip, route === r && s.chipActive]} onPress={() => setRoute(r)}>
            <Text style={[s.chipText, route === r && s.chipTextActive]}>{r}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <Text style={s.label}>Withdrawal period (days)</Text>
      <TextInput style={s.input} value={withdrawal} onChangeText={setWithdrawal} keyboardType="numeric" placeholder="e.g. 7" placeholderTextColor={Colors.textMuted} />

      <Text style={s.label}>Follow-up date</Text>
      <TextInput style={s.input} value={followUpDate} onChangeText={setFollowUpDate} placeholder="YYYY-MM-DD" placeholderTextColor={Colors.textMuted} />

      <Text style={s.label}>Outcome</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: Spacing.md }}>
        {OUTCOMES.map(o => (
          <TouchableOpacity key={o} style={[s.chip, outcome === o && s.chipActive]} onPress={() => setOutcome(o)}>
            <Text style={[s.chipText, outcome === o && s.chipTextActive]}>{OUTCOME_EMOJI[o]} {o}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <Text style={s.label}>Follow-up notes</Text>
      <TextInput style={[s.input, { minHeight: 80 }]} value={followUpNotes} onChangeText={setFollowUpNotes} multiline placeholder="Was there improvement? Any changes?" placeholderTextColor={Colors.textMuted} />

      <Text style={s.label}>Next action</Text>
      <TextInput style={s.input} value={nextAction} onChangeText={setNextAction} placeholder="e.g. Recheck in 5 days, refer to vet" placeholderTextColor={Colors.textMuted} />

      {/* Voice note section */}
      <View style={s.audioSection}>
        <Text style={s.audioTitle}>🎙️ Voice Note</Text>
        <Text style={s.audioSub}>Record a voice note — it will be transcribed automatically</Text>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: Spacing.sm }}>
          {[['en','English'],['sw','Kiswahili'],['fr','Français'],['ar','العربية']].map(([code, label]) => (
            <TouchableOpacity key={code} style={[s.chip, audioLang === code && s.chipActive]} onPress={() => setAudioLang(code)}>
              <Text style={[s.chipText, audioLang === code && s.chipTextActive]}>{label}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        <TouchableOpacity
          style={[s.micBtn, isRecording && s.micBtnActive]}
          onPress={isRecording ? handleStopAndTranscribe : startRecording}
          activeOpacity={0.8}
        >
          {transcribing
            ? <ActivityIndicator color="#fff" />
            : <Text style={s.micBtnText}>{isRecording ? `⏹ Stop (${duration}s)` : '🎙️ Record'}</Text>
          }
        </TouchableOpacity>

        {audioUri && !isRecording && (
          <View style={s.audioPreview}>
            <Text style={s.audioPreviewText}>✅ Audio recorded</Text>
            <TouchableOpacity onPress={clearAudio}><Text style={{ color: Colors.error }}>✕ Remove</Text></TouchableOpacity>
          </View>
        )}

        {!!transcript && (
          <View style={s.transcriptBox}>
            <Text style={s.transcriptLabel}>Transcript:</Text>
            <Text style={s.transcriptText}>{transcript}</Text>
          </View>
        )}
      </View>

      <TouchableOpacity style={[s.saveBtn, saving && { opacity: 0.6 }]} onPress={save} disabled={saving}>
        {saving ? <ActivityIndicator color="#fff" /> : <Text style={s.saveBtnText}>Save Treatment Record</Text>}
      </TouchableOpacity>
    </ScrollView>
  );
}


function TreatmentDetail({ treatment, farm, onBack, onUpdated }: {
  treatment: Treatment; farm: Farm; onBack: () => void; onUpdated: () => void;
}) {
  const [outcome, setOutcome]         = useState(treatment.outcome);
  const [followUpNotes, setFollowUpNotes] = useState(treatment.follow_up_notes);
  const [nextAction, setNextAction]   = useState(treatment.next_action);
  const [saving, setSaving]           = useState(false);

  async function saveFollowUp() {
    setSaving(true);
    try {
      await apiFetch(`/api/farms/${farm.id}/treatments/${treatment.id}`, {
        method: 'PUT',
        body: JSON.stringify({ outcome, follow_up_notes: followUpNotes, next_action: nextAction }),
      });
      onUpdated();
    } catch (err: any) {
      Alert.alert('Error', err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={s.form}>
      <TouchableOpacity onPress={onBack} style={s.backBtn}><Text style={s.backBtnText}>← Back</Text></TouchableOpacity>
      <Text style={s.formTitle}>Treatment Record</Text>

      <View style={s.detailRow}><Text style={s.detailKey}>Date</Text><Text style={s.detailVal}>{new Date(treatment.treatment_date).toLocaleDateString()}</Text></View>
      <View style={s.detailRow}><Text style={s.detailKey}>Animals</Text><Text style={s.detailVal}>{treatment.number_of_animals}</Text></View>
      <View style={s.detailRow}><Text style={s.detailKey}>Diagnosis</Text><Text style={s.detailVal}>{treatment.diagnosis || '—'}</Text></View>
      <View style={s.detailRow}><Text style={s.detailKey}>Treatment</Text><Text style={s.detailVal}>{treatment.treatment_given}</Text></View>
      <View style={s.detailRow}><Text style={s.detailKey}>Dosage</Text><Text style={s.detailVal}>{treatment.dosage || '—'}</Text></View>
      <View style={s.detailRow}><Text style={s.detailKey}>Route</Text><Text style={s.detailVal}>{treatment.route || '—'}</Text></View>
      {treatment.withdrawal_days && <View style={s.detailRow}><Text style={s.detailKey}>Withdrawal</Text><Text style={s.detailVal}>{treatment.withdrawal_days} days</Text></View>}
      {treatment.follow_up_date && <View style={s.detailRow}><Text style={s.detailKey}>Follow-up due</Text><Text style={s.detailVal}>{new Date(treatment.follow_up_date).toLocaleDateString()}</Text></View>}
      {!!treatment.audio_transcript && (
        <View style={s.transcriptBox}>
          <Text style={s.transcriptLabel}>🎙️ Voice note:</Text>
          <Text style={s.transcriptText}>{treatment.audio_transcript}</Text>
        </View>
      )}

      <Text style={[s.label, { marginTop: Spacing.lg }]}>Update outcome</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: Spacing.md }}>
        {OUTCOMES.map(o => (
          <TouchableOpacity key={o} style={[s.chip, outcome === o && s.chipActive]} onPress={() => setOutcome(o)}>
            <Text style={[s.chipText, outcome === o && s.chipTextActive]}>{OUTCOME_EMOJI[o]} {o}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <Text style={s.label}>Follow-up notes</Text>
      <TextInput style={[s.input, { minHeight: 80 }]} value={followUpNotes} onChangeText={setFollowUpNotes} multiline placeholder="Was there improvement?" placeholderTextColor={Colors.textMuted} />

      <Text style={s.label}>Next action</Text>
      <TextInput style={s.input} value={nextAction} onChangeText={setNextAction} placeholder="e.g. Repeat in 5 days" placeholderTextColor={Colors.textMuted} />

      <TouchableOpacity style={[s.saveBtn, saving && { opacity: 0.6 }]} onPress={saveFollowUp} disabled={saving}>
        {saving ? <ActivityIndicator color="#fff" /> : <Text style={s.saveBtnText}>Save Follow-up</Text>}
      </TouchableOpacity>
    </ScrollView>
  );
}


// ─── Main screen ──────────────────────────────────────────────────────────────

export default function FarmScreen() {
  const [screen, setScreen]           = useState<Screen>('farm_list');
  const [selectedFarm, setSelectedFarm] = useState<Farm | null>(null);
  const [selectedTreatment, setSelectedTreatment] = useState<Treatment | null>(null);
  const [refreshKey, setRefreshKey]   = useState(0);
  const { user } = useAuthStore();

  function refresh() { setRefreshKey(k => k + 1); }

  return (
    <SafeAreaView style={s.safe}>
      <View style={s.header}>
        <Text style={s.headerTitle}>Farm Records</Text>
        <Text style={s.headerSub}>Treatment logs and animal management</Text>
      </View>

      {screen === 'farm_list' && (
        <FarmList
          key={refreshKey}
          onSelect={f => { setSelectedFarm(f); setScreen('farm_detail'); }}
          onAdd={() => setScreen('add_farm')}
        />
      )}

      {screen === 'farm_detail' && selectedFarm && (
        <FarmDetail
          key={refreshKey}
          farm={selectedFarm}
          onBack={() => setScreen('farm_list')}
          onAddAnimal={() => setScreen('add_animal')}
          onAddTreatment={() => setScreen('add_treatment')}
          onSelectTreatment={t => { setSelectedTreatment(t); setScreen('treatment_detail'); }}
        />
      )}

      {screen === 'add_farm' && (
        <AddFarmScreen
          onBack={() => setScreen('farm_list')}
          onSaved={() => { refresh(); setScreen('farm_list'); }}
        />
      )}

      {screen === 'add_animal' && selectedFarm && (
        <AddAnimalScreen
          farm={selectedFarm}
          onBack={() => setScreen('farm_detail')}
          onSaved={() => { refresh(); setScreen('farm_detail'); }}
        />
      )}

      {screen === 'add_treatment' && selectedFarm && (
        <AddTreatmentScreen
          farm={selectedFarm}
          onBack={() => setScreen('farm_detail')}
          onSaved={() => { refresh(); setScreen('farm_detail'); }}
        />
      )}

      {screen === 'treatment_detail' && selectedFarm && selectedTreatment && (
        <TreatmentDetail
          farm={selectedFarm}
          treatment={selectedTreatment}
          onBack={() => setScreen('farm_detail')}
          onUpdated={() => { refresh(); setScreen('farm_detail'); }}
        />
      )}
    </SafeAreaView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  safe:        { flex: 1, backgroundColor: Colors.background },
  header:      { backgroundColor: Colors.primary, paddingHorizontal: Spacing.md, paddingTop: Spacing.lg, paddingBottom: Spacing.md },
  headerTitle: { ...Typography.h3, color: '#fff' },
  headerSub:   { ...Typography.caption, color: 'rgba(255,255,255,0.75)', marginTop: 2 },

  list:        { padding: Spacing.md, paddingBottom: 100 },
  card:        { backgroundColor: Colors.surface, borderRadius: Radius.lg, padding: Spacing.md, marginBottom: Spacing.sm, flexDirection: 'row', alignItems: 'center', ...Shadow.sm },
  cardTitle:   { ...Typography.h4, color: Colors.textPrimary },
  cardSub:     { ...Typography.caption, color: Colors.textMuted, marginTop: 2 },
  cardBadge:   { ...Typography.caption, color: Colors.primary, fontWeight: '700' },

  empty:       { alignItems: 'center', paddingTop: 80 },
  emptyEmoji:  { fontSize: 48, marginBottom: Spacing.md },
  emptyTitle:  { ...Typography.h3, color: Colors.textPrimary },
  emptySub:    { ...Typography.body, color: Colors.textMuted, textAlign: 'center', marginTop: 4 },

  fab:         { position: 'absolute', bottom: 24, right: 24, width: 56, height: 56, borderRadius: 28, backgroundColor: Colors.primary, alignItems: 'center', justifyContent: 'center', ...Shadow.lg },
  fabRow:      { position: 'absolute', bottom: 0, right: 0, left: 0 },
  fabText:     { fontSize: 28, color: '#fff', fontWeight: '700' },

  detailHeader:{ backgroundColor: Colors.primary, paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm },
  detailTitle: { ...Typography.h3, color: '#fff' },
  backBtn:     { marginBottom: 4 },
  backBtnText: { ...Typography.body, color: 'rgba(255,255,255,0.8)' },

  tabs:        { flexDirection: 'row', backgroundColor: Colors.surface, borderBottomWidth: 1, borderBottomColor: Colors.border },
  tab:         { flex: 1, paddingVertical: 12, alignItems: 'center' },
  tabActive:   { borderBottomWidth: 2, borderBottomColor: Colors.primary },
  tabText:     { ...Typography.label, color: Colors.textMuted },
  tabTextActive:{ color: Colors.primary },

  form:        { padding: Spacing.lg, paddingBottom: 60 },
  formTitle:   { ...Typography.h2, color: Colors.textPrimary, marginBottom: Spacing.lg },
  label:       { ...Typography.label, color: Colors.textSecondary, marginBottom: 6 },
  input:       { borderWidth: 1, borderColor: Colors.border, borderRadius: Radius.md, paddingHorizontal: Spacing.md, paddingVertical: 11, ...Typography.body, color: Colors.textPrimary, marginBottom: Spacing.md, backgroundColor: Colors.surface },
  saveBtn:     { backgroundColor: Colors.primary, borderRadius: Radius.md, paddingVertical: 15, alignItems: 'center', marginTop: Spacing.md },
  saveBtnText: { ...Typography.h4, color: '#fff' },

  chip:        { borderRadius: Radius.full, borderWidth: 1, borderColor: Colors.border, paddingHorizontal: Spacing.md, paddingVertical: 6, marginRight: Spacing.sm, backgroundColor: Colors.surface },
  chipActive:  { backgroundColor: Colors.primary, borderColor: Colors.primary },
  chipText:    { ...Typography.caption, color: Colors.textSecondary },
  chipTextActive: { color: '#fff' },

  audioSection:  { backgroundColor: Colors.surfaceAlt, borderRadius: Radius.lg, padding: Spacing.md, marginBottom: Spacing.md },
  audioTitle:    { ...Typography.h4, color: Colors.textPrimary, marginBottom: 4 },
  audioSub:      { ...Typography.caption, color: Colors.textMuted, marginBottom: Spacing.sm },
  micBtn:        { backgroundColor: Colors.primary, borderRadius: Radius.md, paddingVertical: 12, alignItems: 'center' },
  micBtnActive:  { backgroundColor: Colors.error },
  micBtnText:    { ...Typography.h4, color: '#fff' },
  audioPreview:  { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: Spacing.sm },
  audioPreviewText: { ...Typography.body, color: Colors.success },

  transcriptBox: { backgroundColor: Colors.background, borderRadius: Radius.md, padding: Spacing.md, marginTop: Spacing.sm, borderWidth: 1, borderColor: Colors.border },
  transcriptLabel:{ ...Typography.label, color: Colors.textMuted, marginBottom: 4 },
  transcriptText: { ...Typography.body, color: Colors.textPrimary },

  detailRow:   { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: Colors.divider },
  detailKey:   { ...Typography.label, color: Colors.textMuted, flex: 1 },
  detailVal:   { ...Typography.body, color: Colors.textPrimary, flex: 2, textAlign: 'right' },
});

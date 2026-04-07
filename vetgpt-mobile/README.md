# VetGPT Mobile

React Native (Expo) app for iOS and Android.
Connects to the VetGPT FastAPI backend with full offline support via on-device LLM.

---

## Project Structure

```
vetgpt-mobile/
│
├── app/                              # Expo Router screens
│   ├── _layout.tsx                   # Root layout — auth restore, network watcher, offline router init
│   ├── download-model.tsx            # Phase 2 — Model download UI (progress, pause, resume)
│   │
│   ├── (auth)/                       # Auth screens (no tab bar)
│   │   ├── _layout.tsx
│   │   ├── login.tsx                 # Email + password login
│   │   └── register.tsx              # Account creation
│   │
│   └── (tabs)/                       # Main app (bottom tab navigator)
│       ├── _layout.tsx               # Tab bar: Chat, Search, Manuals, Profile
│       ├── chat.tsx                  # Core RAG chat with streaming + citations
│       ├── search.tsx                # Direct vector search with species/source filters
│       ├── manuals.tsx               # Browse indexed manual library by category
│       └── profile.tsx               # User info, tier, offline model, settings, logout
│
├── lib/                              # Utilities and API clients
│   ├── api.ts                        # Native fetch client — auth, query, streaming, history
│   ├── modelManager.ts               # Phase 2 — Download/manage Qwen2.5-3B on device
│   ├── localInference.ts             # Phase 2 — llama.cpp + MLC LLM engine clients
│   └── offlineRouter.ts              # Phase 2 — Route: cloud vs local vs unavailable
│
├── store/
│   └── index.ts                      # Zustand — auth state, chat messages, app settings
│
├── constants/
│   └── theme.ts                      # Colors, typography, spacing, shadows, border radius
│
├── assets/                           # App icons and splash (add your own 1024×1024 PNGs)
│   ├── icon.png
│   ├── splash.png
│   ├── adaptive-icon.png
│   └── favicon.png
│
├── app.json                          # Expo config (bundle ID, permissions, plugins)
├── package.json                      # Dependencies — no axios, native fetch only
├── babel.config.js                   # Babel config with Reanimated plugin
├── tsconfig.json                     # TypeScript config
└── .gitignore
```

---

## Setup

```bash
# 1. Install dependencies
npm install

# 2. Add placeholder assets
# Create four 1024×1024 PNG files in assets/:
#   icon.png, splash.png, adaptive-icon.png, favicon.png
# Any solid colour image works as a placeholder

# 3. Update backend URL for your dev machine
# Find your local IP (phone cannot use localhost):
#   Mac/Linux:  ifconfig | grep "inet " | grep -v 127
#   Windows:    ipconfig
# Edit lib/api.ts:
#   const LOCAL_BASE_URL = 'http://192.168.x.x:8000';

# 4. Start dev server
npx expo start

# Scan QR with Expo Go on your phone
# Press 'a' for Android emulator, 'i' for iOS simulator
```

---

## Screens

### Chat (`/chat`)
Streaming RAG chat. Sends query to `offlineRouter` which picks cloud or on-device LLM. Shows citations (source, page, score) and disclaimer below each answer. Offline banner auto-appears when internet is lost. Suggested starter questions shown on empty state.

### Search (`/search`)
Direct vector database search bypassing the chat UI. Species filter chips (Canine, Feline, Bovine, Equine, Ovine, Porcine, Exotic) and source filter chips (WikiVet, PubMed, FAO, Plumb's). Returns AI summary + ranked citation list with match percentages.

### Manuals (`/manuals`)
Library browser grouped into: Open Access (searchable now), Pending License (locked), Upload PDF. Tap an open-access source to search within it. PDF upload hooks into the backend ingestion pipeline (Phase 2).

### Profile (`/profile`)
User info with subscription tier badge. Premium upgrade banner for free users. Streaming and citations toggles. Default species filter. Offline model download button linking to `/download-model`. Sign out.

### Download Model (`/download-model`)
Full model lifecycle UI. Checks storage and WiFi before starting. Shows real-time download progress (bytes + %). Pause, resume, and cancel controls. Verification step after download. Engine info card (MLC for iOS, llama.cpp for Android). Delete model option.

---

## Offline Architecture (Phase 2)

```
Every query → offlineRouter.decide()
    │
    ├── Online ──────────────────────→ Cloud API → Claude / GPT-4o (best quality)
    ├── Offline + iOS + model ready ─→ MLC LLM (Metal GPU, fastest on iPhone)
    ├── Offline + Android + model ───→ llama.cpp (localhost:8080, stable)
    └── Offline + no model ──────────→ Error + prompt to download model
```

**Model:** Qwen2.5-3B-Instruct Q4_K_M
- 1.93 GB (GGUF / llama.cpp) · 2.1 GB (MLC / iOS)
- Requires 4 GB device RAM · Download over WiFi only
- `modelManager.ts` handles download, pause/resume, integrity check, deletion

---

## API Client (`lib/api.ts`)

Native `fetch` only — no axios.

```typescript
// Auth
await register("vet@clinic.com", "password", "Dr Smith");
await login("vet@clinic.com", "password");
await logout();
const user = await getMe();

// Query
const result = await queryVet("canine parvovirus treatment", {
  top_k: 5,
  filter_species: "canine",
});

// Streaming
await streamQuery("equine colic signs",
  (token) => append(token),
  () => done(),
  (err) => handleError(err),
);

// History
const history = await getHistory(20, 0);
```

JWT is auto-attached from `expo-secure-store`. 401 auto-clears the token.

---

## State Management

| Store | Key state | Key actions |
|-------|-----------|-------------|
| `useAuthStore` | `user`, `isAuthenticated` | `setUser`, `logout` |
| `useChatStore` | `messages`, `isQuerying` | `addMessage`, `updateLastMessage`, `newSession` |
| `useAppStore` | `isOnline`, `hasLocalModel`, filters | `setOnline`, `setHasLocalModel`, `setFilterSpecies` |

---

## Native Modules Note (Phase 2)

`llama.rn` and `react-native-mlc-llm` are native modules — Expo Go will not work for Phase 2.

```bash
# Generate native projects
npx expo prebuild

# Run on device/emulator
npx expo run:android
npx expo run:ios          # Mac + Xcode required

# Production build via EAS
eas build --platform all
```

Phase 1 features (chat, search, auth) work fully in Expo Go.

---

## .gitignore

```
node_modules/
.expo/
dist/
ios/
android/
*.jks
*.p8
*.p12
*.key
*.mobileprovision
web-build/
.env
assets/models/
```

---

## Phase Status

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Login + Register | ✅ Complete |
| 1 | Chat (streaming + citations) | ✅ Complete |
| 1 | Search (species + source filters) | ✅ Complete |
| 1 | Manuals browser | ✅ Complete |
| 1 | Profile + settings | ✅ Complete |
| 1 | JWT auth via SecureStore | ✅ Complete |
| 1 | Native fetch API client | ✅ Complete |
| 1 | Zustand state management | ✅ Complete |
| 1 | Network monitoring | ✅ Complete |
| 2 | Model download screen | ✅ Complete |
| 2 | ModelManager (download/pause/resume) | ✅ Complete |
| 2 | llama.cpp client (Android + iOS) | ✅ Complete |
| 2 | MLC LLM client (iOS Metal GPU) | ✅ Complete |
| 2 | Offline router | ✅ Complete |
| 2 | expo prebuild + dev build | ⏳ Run on your machine |
| 2 | Bundled local vector DB (sqlite-vec) | 🔲 Planned |
| 3 | Camera capture + OCR (ML Kit) | 🔲 Planned |
| 3 | Image recognition — lesions/wounds | 🔲 Planned |
| 3 | X-ray DICOM upload + AI (premium) | 🔲 Planned |
| 3 | Stripe paywall + in-app purchase | 🔲 Planned |

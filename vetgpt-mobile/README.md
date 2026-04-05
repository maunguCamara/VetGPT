# VetGPT Mobile App

React Native (Expo) app for iOS and Android.

## Project Structure

```
vetgpt-mobile/
├── app/
│   ├── _layout.tsx          Root layout — auth check + network watcher
│   ├── (auth)/
│   │   ├── login.tsx        Login screen
│   │   └── register.tsx     Register screen
│   └── (tabs)/
│       ├── _layout.tsx      Tab navigator (Chat, Search, Manuals, Profile)
│       ├── chat.tsx         ← Main RAG chat interface
│       ├── search.tsx       Direct vector search with filters
│       ├── manuals.tsx      Browse indexed manual library
│       └── profile.tsx      User settings, tier, offline model
├── constants/
│   └── theme.ts             Colors, typography, spacing
├── lib/
│   └── api.ts               Axios client + streaming + auth
├── store/
│   └── index.ts             Zustand — auth, chat, app state
├── assets/                  Icons, splash screen (add your own)
├── app.json                 Expo config
├── package.json
└── babel.config.js
```

## Setup

```bash
# 1. Install dependencies
npm install

# 2. Add placeholder assets (required by Expo)
mkdir -p assets
# Create 1024x1024 icon.png, splash.png, adaptive-icon.png, favicon.png
# Use any image editor or Expo's asset generator

# 3. Start the dev server
npx expo start

# Scan QR code with Expo Go app on your phone
# Or press 'a' for Android emulator, 'i' for iOS simulator
```

## Connecting to Backend

Edit `lib/api.ts`:

```typescript
const LOCAL_BASE_URL = 'http://YOUR_LOCAL_IP:8000';  // not localhost — use your machine's IP
```

Find your IP:
- Mac/Linux: `ifconfig | grep inet`
- Windows:   `ipconfig`

## Building for Production

```bash
# Install EAS CLI
npm install -g eas-cli

# Login to Expo
eas login

# Configure build
eas build:configure

# Build for both platforms
eas build --platform all
```

## Features by Screen

### Chat (`/chat`)
- Streaming RAG responses with typing effect
- Citation panel below each answer (source + page)
- Offline banner + graceful degradation
- 5 suggested starter questions
- Premium image upload button (camera icon)
- New session / clear chat

### Search (`/search`)
- Direct vector search (bypasses chat UI)
- Species filter chips (Canine, Feline, Bovine, Equine...)
- Source filter chips (WikiVet, PubMed, FAO, Plumb's)
- Full citation list with match scores

### Manuals (`/manuals`)
- Grouped list: Available Now / Pending License / Upload
- Tap open-access sources to search within them
- Upload PDF (Phase 2)

### Profile (`/profile`)
- User info + subscription tier badge
- Premium upgrade banner (free users)
- Streaming / citations toggles
- Default species filter setting
- Offline model download placeholder (Phase 2)
- Sign out

## Phase 2 Additions (Offline)
- [ ] Download Qwen2.5-3B weights on-device
- [ ] llama.cpp local server integration
- [ ] Auto-route: offline → local model, online → cloud
- [ ] Local vector DB (sqlite-vec) with bundled index

## Phase 3 Additions (Premium Vision)
- [ ] Camera capture → OCR (Google ML Kit)
- [ ] Image upload → vision analysis (GPT-4o Vision)
- [ ] X-ray DICOM upload + AI analysis

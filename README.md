# VetGPT Bots

WhatsApp and Telegram chatbot interfaces for VetGPT.

Both bots reuse the same RAG pipeline as the mobile app — no duplicate AI logic.
They POST to `/api/query` on your FastAPI backend and relay the answer.

---

## Architecture

```
User (WhatsApp / Telegram)
        │
        ▼
Twilio / Telegram servers
        │
        ▼
VetGPT Bot (this service)
        │
        ▼
POST /api/query  →  ChromaDB + LLM  →  Answer + Citations
        │
        ▼
User receives formatted answer
```

---

## Telegram Setup

### 1. Create bot

1. Open Telegram → message **@BotFather**
2. Send `/newbot`
3. Choose a name: `VetGPT`
4. Choose a username: `vetgpt_bot` (must end in `bot`)
5. Copy the token

### 2. Configure

```bash
# .env
TELEGRAM_BOT_TOKEN=1234567890:AAFxxxxxxxxxxxxxxxxxxxxxx
VETGPT_API_URL=http://localhost:8000
BOT_API_KEY=your-dedicated-bot-jwt-token
```

### 3. Run (development — polling)

```bash
pip install python-telegram-bot==21.3
python -m bots.telegram_bot
```

Your bot is now live. Find it on Telegram by username and message it.

### 4. Run (production — webhook)

```bash
# .env additions
TELEGRAM_WEBHOOK_URL=https://api.vetgpt.app/telegram/webhook
TELEGRAM_WEBHOOK_PORT=8443
TELEGRAM_WEBHOOK_SECRET=random-32-char-secret

# Docker
docker compose --profile bots up -d telegram-bot
```

### Bot commands

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/help` | Usage guide |
| `/language sw` | Switch to Swahili |
| `/sources` | List knowledge sources |
| `/disclaimer` | Clinical disclaimer |
| `/subscribe` | Link to premium upgrade |

---

## WhatsApp Setup

### Option A — Twilio (recommended, works immediately)

#### 1. Create Twilio account

1. Sign up at [twilio.com](https://twilio.com)
2. Go to **Messaging → Try it out → Send a WhatsApp message**
3. Follow sandbox activation — send the join code from your phone
4. Note your sandbox number (e.g. `+1 415 523 8886`)

#### 2. Configure webhook

In Twilio Console → Messaging → Settings → WhatsApp Sandbox Settings:
```
Webhook URL: https://api.vetgpt.app/bots/whatsapp/webhook
HTTP Method: POST
```

#### 3. Configure

```bash
# .env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
VETGPT_API_URL=http://localhost:8000
BOT_API_KEY=your-dedicated-bot-jwt-token
```

#### 4. Run

The WhatsApp webhook is mounted directly in FastAPI — no separate process needed:

```bash
uvicorn backend.main:app --reload --port 8000
# WhatsApp webhook is live at: POST /bots/whatsapp/webhook
```

#### 5. Production WhatsApp Business number

To get your own WhatsApp number (not sandbox):
1. Twilio Console → Messaging → Senders → WhatsApp Senders
2. Apply for a WhatsApp Business Account
3. Approval: 1–5 business days
4. Update `TWILIO_WHATSAPP_FROM=whatsapp:+254XXXXXXXXX`

### Option B — Meta Cloud API (direct, no Twilio)

Requires Meta Business verification (~2 weeks).
See `bots/whatsapp_meta.py` for that implementation (not built yet).

### WhatsApp commands

Users send these as plain text messages:

| Message | Action |
|---|---|
| `hi` / `hello` / `start` | Welcome message |
| `help` | Usage guide |
| `language sw` | Switch to Swahili |
| `language en` | Switch to English |
| `sources` | List knowledge sources |
| `disclaimer` | Clinical notice |
| Any other text | VetGPT RAG query |

---

## Creating the BOT_API_KEY

The bots need a JWT token to authenticate with your API.
Create a dedicated user account for them:

```bash
# 1. Register a bot user via your API
curl -X POST https://api.vetgpt.app/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"bot@vetgpt.app","password":"strong-password","full_name":"VetGPT Bot"}'

# 2. Copy the access_token from the response
# 3. Upgrade it to clinic tier via admin endpoint:
curl -X PUT https://api.vetgpt.app/api/admin/users/{user_id}/tier \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -d '{"tier":"clinic"}'

# 4. Add the token to .env:
BOT_API_KEY=eyJhbGciOiJIUzI1NiJ9...
```

The clinic tier gives bots 500 queries/minute — plenty for production load.

---

## Supported Languages

Both bots support 7 languages. The LLM auto-detects the query language.
Users can also explicitly set their preference.

| Code | Language | Command |
|---|---|---|
| `en` | English | `language en` |
| `sw` | Kiswahili | `language sw` |
| `fr` | Français | `language fr` |
| `ar` | العربية | `language ar` |
| `pt` | Português | `language pt` |
| `es` | Español | `language es` |
| `zh` | 中文 | `language zh` |

---

## Production Docker

```bash
# Run API + Telegram bot
docker compose --profile production --profile bots up -d

# Logs
docker logs vetgpt_telegram -f
docker logs vetgpt_api -f
```

WhatsApp webhook runs inside the main API container — no separate service needed.

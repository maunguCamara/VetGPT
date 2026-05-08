"""
vetgpt/bots/whatsapp_bot.py

VetGPT WhatsApp Bot via Twilio WhatsApp Business API.

Twilio is the easiest production-ready WhatsApp integration:
  - Official WhatsApp Business API access
  - No Meta Business verification needed to start (Sandbox for dev)
  - Simple webhook — POST to your URL on each message

Alternative: Meta Cloud API (direct, but requires Meta Business verification).
See whatsapp_meta.py for that implementation.

Features:
  - Any text → VetGPT RAG query → answer with references
  - "language en/sw/fr/ar/pt/es/zh" → set language
  - "help" → usage guide
  - "sources" → knowledge sources
  - Image messages → prompt to use mobile app
  - Multilingual (7 languages)
  - Per-user language preference (in-memory, use Redis in production)

Architecture:
  WhatsApp → Twilio → POST /bots/whatsapp/webhook → VetGPT API → Twilio → WhatsApp

Setup:
  1. Sign up at twilio.com → Get WhatsApp Sandbox number
  2. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM in .env
  3. Point Twilio webhook to: https://api.vetgpt.app/bots/whatsapp/webhook
  4. The WhatsApp router is mounted in main.py at /bots/whatsapp

Production (WhatsApp Business Account):
  Apply for a WhatsApp Business Account in Twilio console.
  Approval takes 1-5 business days.

Install:
  pip install twilio httpx

"""

import os
import logging
import hashlib
import hmac
import httpx

from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import PlainTextResponse

log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

TWILIO_ACCOUNT_SID    = os.getenv("TWILIO_ACCOUNT_SID",    "")
TWILIO_AUTH_TOKEN     = os.getenv("TWILIO_AUTH_TOKEN",     "")
TWILIO_WHATSAPP_FROM  = os.getenv("TWILIO_WHATSAPP_FROM",  "whatsapp:+14155238886")  # Twilio sandbox
VETGPT_API_URL        = os.getenv("VETGPT_API_URL",        "http://localhost:8009")
BOT_API_KEY           = os.getenv("BOT_API_KEY",           "")

SUPPORTED_LANGUAGES = {
    "en": "English 🇺🇸",
    "sw": "Kiswahili 🇰🇪",
    "fr": "Français 🇫🇷",
    "ar": "العربية 🇸🇦",
    "pt": "Português 🇵🇹",
    "es": "Español 🇪🇸",
    "zh": "中文 🇨🇳",
}

WELCOME = (
    "🐾 *Welcome to VetGPT!*\n\n"
    "I'm an AI veterinary reference assistant.\n\n"
    "Just type your question — in any language. Examples:\n"
    "• What causes bovine respiratory disease?\n"
    "• Dalili za parvovirus kwa mbwa?\n"
    "• Dosis amoxicilina perro 10kg\n\n"
    "*Commands:*\n"
    "• `help` — usage guide\n"
    "• `language sw` — switch to Swahili\n"
    "• `sources` — what I know\n"
    "• `disclaimer` — clinical notice\n\n"
    "⚠️ _Reference only. Always consult a licensed vet._"
)

# ─── Per-user state (use Redis in production) ─────────────────────────────────

user_language: dict[str, str] = {}   # phone_number → language code

# ─── Router ───────────────────────────────────────────────────────────────────

whatsapp_router = APIRouter(prefix="/bots/whatsapp", tags=["bots"])


# ─── Twilio webhook signature validation ──────────────────────────────────────

def validate_twilio_signature(request_url: str, post_params: dict, signature: str) -> bool:
    """
    Validate that the webhook came from Twilio, not a third party.
    https://www.twilio.com/docs/usage/webhooks/webhooks-security
    """
    if not TWILIO_AUTH_TOKEN:
        return True   # skip validation if token not configured (dev only)

    # Build validation string: URL + sorted POST params
    s = request_url
    for k, v in sorted(post_params.items()):
        s += k + v

    expected = hmac.new(
        TWILIO_AUTH_TOKEN.encode("utf-8"),
        s.encode("utf-8"),
        hashlib.sha1,
    ).digest()

    import base64
    expected_b64 = base64.b64encode(expected).decode("utf-8")
    return hmac.compare_digest(expected_b64, signature)


# ─── API client ───────────────────────────────────────────────────────────────

async def query_vetgpt(question: str, language: str = "en") -> dict:
    headers = {}
    if BOT_API_KEY:
        headers["Authorization"] = f"Bearer {BOT_API_KEY}"

    async with httpx.AsyncClient(timeout=360) as client:  # 6 min — matches Ollama cold start
        resp = await client.post(
            f"{VETGPT_API_URL}/api/query",
            json={"query": question, "top_k": 5, "language": language},
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


def format_for_whatsapp(data: dict) -> str:
    """
    Format VetGPT response for WhatsApp.
    WhatsApp supports *bold*, _italic_, ~strikethrough~, `monospace`.
    No markdown headers. Max 4096 chars per message.
    """
    answer    = data.get("answer", "No answer returned.")
    citations = data.get("citations", [])
    latency   = data.get("latency_ms", 0)

    # Trim to WhatsApp limit
    if len(answer) > 3200:
        answer = answer[:3200] + "...\n_(Truncated — ask for more)_"

    text = answer

    if citations:
        text += "\n\n📚 *References:*"
        for i, c in enumerate(citations[:5], 1):
            title = c.get("document_title", "Unknown")
            page  = c.get("page_number", "?")
            score = c.get("score", 0)
            text += f"\n[{i}] {title} — p.{page} ({score:.0%})"

    text += f"\n\n⏱ {latency}ms · ⚠️ _Reference only — consult a vet_"
    return text


async def send_whatsapp(to: str, body: str) -> None:
    """Send WhatsApp message via Twilio REST API."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        log.warning("Twilio credentials not configured — message not sent")
        return

    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
            data={
                "From": TWILIO_WHATSAPP_FROM,
                "To":   to,
                "Body": body,
            },
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            timeout=15,
        )


# ─── Webhook endpoint ─────────────────────────────────────────────────────────

@whatsapp_router.post("/webhook", response_class=PlainTextResponse)
async def whatsapp_webhook(
    request: Request,
    Body:        str = Form(default=""),
    From:        str = Form(default=""),
    To:          str = Form(default=""),
    MediaUrl0:   str = Form(default=""),   # image URL if sent
    NumMedia:    str = Form(default="0"),
):
    """
    Twilio WhatsApp webhook.
    Twilio POSTs form data here on every incoming message.
    We respond with an empty 200 OK and send the reply asynchronously.
    """
    # Validate Twilio signature
    sig = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    params = dict(await request.form())

    if sig and not validate_twilio_signature(url, dict(params), sig):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    sender   = From.strip()
    text     = Body.strip()
    language = user_language.get(sender, "en")

    # Respond 200 immediately — Twilio expects fast response
    # Process asynchronously below
    log.info(f"[WhatsApp] {sender}: {text[:80]}")

    # ── Image received ────────────────────────────────────────────────────────
    if int(NumMedia) > 0:
        await send_whatsapp(
            sender,
            "📷 Image received!\n\n"
            "AI image analysis (X-ray, wounds, lesions) is available in the "
            "VetGPT mobile app for Premium users.\n"
            "Download: vetgpt.app",
        )
        return ""

    # ── Commands ──────────────────────────────────────────────────────────────
    lower = text.lower().strip()

    if lower in ("hi", "hello", "start", "/start", "habari", "hola", "salut", "مرحبا"):
        await send_whatsapp(sender, WELCOME)
        return ""

    if lower in ("help", "msaada", "aide", "ayuda"):
        help_text = (
            "🐾 *VetGPT Help*\n\n"
            "Type any veterinary question — in any language.\n\n"
            "*Commands:*\n"
            "• `language sw` — switch language (en/sw/fr/ar/pt/es/zh)\n"
            "• `sources` — knowledge sources\n"
            "• `disclaimer` — clinical notice\n"
            "• `help` — this message\n\n"
            "*Example questions:*\n"
            "• Signs of canine parvovirus?\n"
            "• Dalili za homa ya nguruwe?\n"
            "• Dose amoxicilina vacas?\n\n"
            "⚠️ _Always consult a licensed veterinarian._"
        )
        await send_whatsapp(sender, help_text)
        return ""

    if lower in ("sources", "vyanzo", "sources"):
        sources = (
            "📚 *VetGPT Knowledge Sources*\n\n"
            "✅ Available:\n"
            "• WikiVet (CC BY-SA)\n"
            "• PubMed research abstracts\n"
            "• FAO livestock manuals\n"
            "• eClinPath (Cornell University)\n\n"
            "⏳ Pending license:\n"
            "• Merck Veterinary Manual\n"
            "• Plumb's Drug Handbook\n\n"
            "💡 Upload your own PDFs via the mobile app."
        )
        await send_whatsapp(sender, sources)
        return ""

    if lower in ("disclaimer", "onyo"):
        await send_whatsapp(
            sender,
            "⚠️ *Clinical Disclaimer*\n\n"
            "VetGPT provides AI-generated reference information only.\n"
            "It does NOT replace professional veterinary diagnosis or treatment.\n"
            "Always consult a licensed veterinarian before making clinical decisions.\n"
            "Drug dosages must be verified against current formularies."
        )
        return ""

    # language command: "language sw" or "lugha sw"
    if lower.startswith("language ") or lower.startswith("lugha "):
        parts = lower.split()
        if len(parts) == 2 and parts[1] in SUPPORTED_LANGUAGES:
            code  = parts[1]
            user_language[sender] = code
            label = SUPPORTED_LANGUAGES[code]
            await send_whatsapp(
                sender,
                f"✅ Language set to *{label}*\n\nNow ask me any veterinary question!"
            )
        else:
            lang_list = "\n".join(f"• `language {k}` — {v}" for k, v in SUPPORTED_LANGUAGES.items())
            await send_whatsapp(
                sender,
                f"🌍 *Available languages:*\n\n{lang_list}"
            )
        return ""

    # ── VetGPT query ──────────────────────────────────────────────────────────
    if not text:
        return ""

    try:
        data     = await query_vetgpt(text, language=language)
        response = format_for_whatsapp(data)
        await send_whatsapp(sender, response)

    except httpx.TimeoutException:
        await send_whatsapp(
            sender,
            "⏳ AI model is loading (first query only). Please resend in 30 seconds."
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            await send_whatsapp(sender, "🚦 Too many requests. Please wait a moment.")
        else:
            log.error(f"API error: {e.response.status_code}")
            await send_whatsapp(sender, "❌ Something went wrong. Try again in a moment.")
    except Exception as e:
        log.error(f"WhatsApp handler error: {e}")
        await send_whatsapp(sender, "❌ An error occurred. Please try again.")

    return ""


# ─── Health check ─────────────────────────────────────────────────────────────

@whatsapp_router.get("/health")
async def whatsapp_health():
    return {
        "status":     "ok",
        "configured": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN),
        "from":       TWILIO_WHATSAPP_FROM,
        "api_url":    VETGPT_API_URL,
    }
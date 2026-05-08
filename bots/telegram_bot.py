"""
vetgpt/bots/telegram_bot.py

VetGPT Telegram Bot.

Features:
  - /start           — welcome message with instructions
  - /help            — usage guide
  - /language [code] — set preferred response language (en, sw, fr, ar, pt, es, zh)
  - /sources         — list indexed knowledge sources
  - /disclaimer      — show clinical disclaimer
  - Any text message → VetGPT RAG query → answer with citations
  - Image messages   → forwarded to vision API (premium users)
  - /subscribe       — link to upgrade page

Architecture:
  Telegram → this bot → POST /api/query (FastAPI) → LLM answer → Telegram

Setup:
  1. Message @BotFather on Telegram → /newbot → copy token
  2. Set TELEGRAM_BOT_TOKEN in .env
  3. Set VETGPT_API_URL to your backend URL
  4. Run: python bots/telegram_bot.py

Production (webhook mode):
  Set TELEGRAM_WEBHOOK_URL to your public HTTPS URL.
  The bot will register itself and use webhooks instead of polling.

Install:
  pip install python-telegram-bot==21.3 httpx

"""

import os
import asyncio
import logging
import httpx
from typing import Optional
from dotenv import load_dotenv
load_dotenv()  # load .env from project root

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, MenuButtonCommands,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler,
)
from telegram.constants import ParseMode, ChatAction

logging.basicConfig(
    format="%(asctime)s [TelegramBot] %(levelname)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN",  "")
VETGPT_API_URL      = os.getenv("VETGPT_API_URL",       "http://localhost:8000")
TELEGRAM_WEBHOOK_URL = os.getenv("TELEGRAM_WEBHOOK_URL", "")  # set for production
BOT_API_KEY         = os.getenv("BOT_API_KEY",          "")   # optional: dedicated bot user JWT

SUPPORTED_LANGUAGES = {
    "en": "🇺🇸 English",
    "sw": "🇰🇪 Kiswahili",
    "fr": "🇫🇷 Français",
    "ar": "🇸🇦 العربية",
    "pt": "🇵🇹 Português",
    "es": "🇪🇸 Español",
    "zh": "🇨🇳 中文",
}

WELCOME_MESSAGE = """🐾 *Welcome to VetGPT!*

I'm an AI veterinary reference assistant. Ask me about:
• Disease diagnosis and clinical signs
• Drug dosages and treatment protocols  
• Surgical procedures
• Laboratory results interpretation
• Livestock and companion animal medicine

Just type your question in any language and I'll answer using indexed veterinary references.

*Commands:*
/help — usage guide
/language — change response language
/sources — what I know
/disclaimer — important notice

_⚠️ For reference only. Always consult a licensed veterinarian._"""

DISCLAIMER = """⚠️ *Clinical Disclaimer*

VetGPT provides AI-generated veterinary reference information compiled from:
• WikiVet (CC BY-SA)
• PubMed research abstracts
• FAO livestock manuals
• eClinPath (Cornell University)
• Uploaded veterinary textbooks

*This information is for reference purposes only.*
It does not constitute veterinary diagnosis or treatment advice.
Always consult a qualified, licensed veterinarian before making clinical decisions.

Drug dosages should be verified against current formularies (e.g. Plumb's Veterinary Drug Handbook)."""

# ─── In-memory user state (use Redis in production) ───────────────────────────

user_language: dict[int, str] = {}    # user_id → language code
user_history:  dict[int, list] = {}   # user_id → recent queries (for context)


# ─── API client ───────────────────────────────────────────────────────────────

async def query_vetgpt(
    question: str,
    language: str = "en",
    user_id: Optional[int] = None,
) -> dict:
    """Call VetGPT RAG API and return the response dict."""
    headers = {}
    if BOT_API_KEY:
        headers["Authorization"] = f"Bearer {BOT_API_KEY}"

    payload = {
        "query":    question,
        "top_k":    5,
        "language": language,
    }

    async with httpx.AsyncClient(timeout=360) as client:  # 6 min — matches Ollama cold start
        resp = await client.post(
            f"{VETGPT_API_URL}/api/query",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


def format_response(data: dict, language: str) -> str:
    """Format API response for Telegram markdown."""
    answer    = data.get("answer", "No answer returned.")
    citations = data.get("citations", [])
    latency   = data.get("latency_ms", 0)

    # Truncate very long answers for Telegram's 4096 char limit
    if len(answer) > 3500:
        answer = answer[:3500] + "...\n\n_(Answer truncated — ask for more details)_"

    text = answer

    # Add numbered references if present
    if citations:
        refs = "\n\n📚 *References:*"
        for i, c in enumerate(citations[:5], 1):
            title  = c.get("document_title", "Unknown source")
            page   = c.get("page_number", "?")
            score  = c.get("score", 0)
            refs  += f"\n[{i}] {title} — p.{page} _{score:.0%} match_"
        text += refs

    # Footer
    text += f"\n\n⏱ _{latency}ms_ · ⚠️ _Reference only — consult a vet_"

    return text


# ─── Command handlers ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        WELCOME_MESSAGE,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🌍 Choose language", callback_data="pick_lang"),
            InlineKeyboardButton("❓ Help", callback_data="show_help"),
        ]]),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = """🐾 *VetGPT Help*

*How to use:*
Simply type any veterinary question. Examples:
• "What are the signs of canine parvovirus?"
• "Dawa ya BRD ng'ombe ni ipi?" _(Swahili)_
• "Dose de amoxicilina para cão de 10kg" _(Portuguese)_

*Commands:*
/start — welcome screen
/language — set response language
/sources — knowledge sources
/disclaimer — clinical notice

*Tips:*
• Be specific — include species, weight, age when relevant
• Ask follow-up questions in the same chat
• For drug dosages, always verify with your formulary

*Premium features (mobile app):*
• X-ray & DICOM analysis
• Wound/lesion recognition
• Parasite identification
• Cytology interpretation
Download at: vetgpt.app"""

    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


async def cmd_language(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Show language picker."""
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"lang_{code}")]
        for code, label in SUPPORTED_LANGUAGES.items()
    ]
    await update.message.reply_text(
        "🌍 *Choose your preferred response language:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cmd_sources(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    sources_text = """📚 *VetGPT Knowledge Sources*

✅ *Available now (open access):*
• WikiVet — full veterinary encyclopedia (CC BY-SA)
• PubMed — research abstracts (public domain)  
• FAO — livestock & animal health manuals
• eClinPath — clinical pathology (Cornell CVM)

⏳ *Pending license:*
• Merck Veterinary Manual
• Plumb's Drug Handbook
• Blackwell's 5-Min Consult
• Fossum Small Animal Surgery
• Jubb, Kennedy & Palmer Pathology

💡 _Upload your own PDFs via the mobile app_"""

    await update.message.reply_text(sources_text, parse_mode=ParseMode.MARKDOWN)


async def cmd_disclaimer(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(DISCLAIMER, parse_mode=ParseMode.MARKDOWN)


async def cmd_subscribe(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "⭐ *Upgrade to VetGPT Premium*\n\n"
        "Unlock AI image analysis — X-ray, wound, lesion, parasite, cytology.\n\n"
        "→ [vetgpt.app/upgrade](https://vetgpt.app/upgrade)",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── Callback query handler (inline buttons) ──────────────────────────────────

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data    = query.data
    user_id = query.from_user.id

    if data == "pick_lang":
        buttons = [
            [InlineKeyboardButton(label, callback_data=f"lang_{code}")]
            for code, label in SUPPORTED_LANGUAGES.items()
        ]
        await query.edit_message_text(
            "🌍 *Choose your preferred response language:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif data.startswith("lang_"):
        code = data.split("_", 1)[1]
        if code in SUPPORTED_LANGUAGES:
            user_language[user_id] = code
            label = SUPPORTED_LANGUAGES[code]
            await query.edit_message_text(
                f"✅ Language set to *{label}*\n\nNow ask me any veterinary question!",
                parse_mode=ParseMode.MARKDOWN,
            )

    elif data == "show_help":
        await query.edit_message_text(
            "Just type any veterinary question and I'll answer using indexed vet references.\n\n"
            "Use /help for detailed usage guide.",
        )


# ─── Message handler ──────────────────────────────────────────────────────────

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle any text message — query VetGPT and reply."""
    user_id  = update.effective_user.id
    question = (update.message.text or "").strip()

    if not question:
        return

    language = user_language.get(user_id, "en")

    # Show typing indicator
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        data     = await query_vetgpt(question, language=language, user_id=user_id)
        response = format_response(data, language)

        await update.message.reply_text(
            response,
            parse_mode=ParseMode.MARKDOWN,
        )

    except httpx.TimeoutException:
        await update.message.reply_text(
            "⏳ The AI model is loading — this only happens once after restart.\n\n"
            "Please resend your question in 30 seconds and it will respond immediately."
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            await update.message.reply_text(
                "🚦 Too many requests. Please wait a moment and try again."
            )
        else:
            log.error(f"API error {e.response.status_code}: {e.response.text}")
            await update.message.reply_text(
                "❌ Something went wrong. Please try again in a moment."
            )
    except Exception as e:
        log.error(f"Unexpected error: {e}")
        await update.message.reply_text(
            "❌ An error occurred. Please try again."
        )


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle image messages — prompt to use mobile app for vision features."""
    await update.message.reply_text(
        "📷 *Image received!*\n\n"
        "AI image analysis (X-ray, wounds, lesions, parasites, cytology) "
        "is available in the *VetGPT mobile app* for Premium users.\n\n"
        "Download: vetgpt.app\n"
        "Upgrade: /subscribe",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── Error handler ────────────────────────────────────────────────────────────

async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    log.error(f"Update caused error: {ctx.error}", exc_info=ctx.error)


# ─── Bot setup ────────────────────────────────────────────────────────────────

async def post_init(app: Application) -> None:
    """Set bot commands menu."""
    await app.bot.set_my_commands([
        BotCommand("start",      "Welcome and instructions"),
        BotCommand("help",       "Usage guide"),
        BotCommand("language",   "Set response language"),
        BotCommand("sources",    "Knowledge sources"),
        BotCommand("disclaimer", "Clinical disclaimer"),
        BotCommand("subscribe",  "Upgrade to Premium"),
    ])


def build_app() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN not set. "
            "Get one from @BotFather on Telegram and add to .env"
        )

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Commands
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("help",       cmd_help))
    app.add_handler(CommandHandler("language",   cmd_language))
    app.add_handler(CommandHandler("sources",    cmd_sources))
    app.add_handler(CommandHandler("disclaimer", cmd_disclaimer))
    app.add_handler(CommandHandler("subscribe",  cmd_subscribe))

    # Callbacks (inline buttons)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Errors
    app.add_error_handler(error_handler)

    return app


def run():
    app = build_app()

    if TELEGRAM_WEBHOOK_URL:
        # Production: webhook mode (more efficient, no polling)
        log.info(f"Starting webhook mode: {TELEGRAM_WEBHOOK_URL}")
        app.run_webhook(
            listen      = "0.0.0.0",
            port        = int(os.getenv("TELEGRAM_WEBHOOK_PORT", "8443")),
            secret_token = os.getenv("TELEGRAM_WEBHOOK_SECRET", ""),
            webhook_url  = TELEGRAM_WEBHOOK_URL,
        )
    else:
        # Development: polling mode (no public URL needed)
        log.info("Starting polling mode (dev)")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()
"""
Telegram Welcome Bot  (Supabase-editable edition)
-------------------------------------------------
Greets each person by name and shows tappable buttons.

Pipeline:  GitHub (code) -> Supabase (database) -> Railway (hosting) -> Telegram (bot)

NEW: the welcome text and the buttons now live in Supabase, so you can change
them anytime in the dashboard (Table Editor -> bot_settings / buttons) and the
very next greeting uses the new version. No code edits, no redeploy.

  - Table "bot_settings": the row 'welcome_text' holds the message.
      * Keep {name} where the member's name should appear.
      * *asterisks* make text bold.
  - Table "buttons": one row per button (sort_order, label, url).
      * Add a row = new button. Delete a row = button gone.
  - Table "members": everyone the bot has greeted (filled automatically).

If Supabase is ever unreachable, the bot falls back to the DEFAULT_ text
below, so greetings never stop.

Configuration comes from ENVIRONMENT VARIABLES (never hardcode secrets):
  BOT_TOKEN      - from @BotFather
  SUPABASE_URL   - Supabase project URL        (Settings -> API)
  SUPABASE_KEY   - Supabase service_role key   (Settings -> API, keep secret)
"""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from supabase import Client, create_client
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
)

load_dotenv()  # loads a local .env file; on Railway, variables are injected for you

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("welcome-bot")

# =============================================================
#  CONFIG - secrets come from the environment
# =============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

_missing = [
    name
    for name, value in {
        "BOT_TOKEN": BOT_TOKEN,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": SUPABASE_KEY,
    }.items()
    if not value
]
if _missing:
    sys.exit(
        f"Missing environment variables: {', '.join(_missing)}. "
        "Add them in Railway (Variables tab) or in a local .env file."
    )

# =============================================================
#  FALLBACKS - used only if Supabase can't be reached.
#  The REAL text lives in Supabase (Table Editor -> bot_settings).
# =============================================================

DEFAULT_WELCOME_TEXT = (
    "\U0001F44B *Welcome to our community, {name}!*\n\n"
    "To get started, please:\n\n"
    "1\uFE0F\u20E3 Read the pinned rules\n"
    "2\uFE0F\u20E3 Introduce yourself\n"
    "3\uFE0F\u20E3 Check out our resources\n"
)

DEFAULT_BUTTONS = [
    ("\U0001F4D6 Read the Rules", "https://example.com/rules"),
    ("\U0001F4AC Join the Chat", "https://t.me/yourchat"),
    ("\U0001F310 Our Website", "https://example.com"),
]

# =============================================================
#  SUPABASE
# =============================================================

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def _fetch_welcome_config():
    """Read the current welcome text and buttons from Supabase (sync client)."""
    text = DEFAULT_WELCOME_TEXT
    buttons = DEFAULT_BUTTONS

    try:
        res = (
            supabase.table("bot_settings")
            .select("value")
            .eq("key", "welcome_text")
            .limit(1)
            .execute()
        )
        if res.data and res.data[0].get("value"):
            # Accept both real line breaks and a typed "\n" in the Table Editor.
            text = res.data[0]["value"].replace("\\n", "\n")
    except Exception:
        log.exception("Could not load welcome_text from Supabase; using default")

    try:
        res = (
            supabase.table("buttons")
            .select("label, url")
            .order("sort_order")
            .execute()
        )
        # An empty table means "no buttons, on purpose" - that's allowed.
        buttons = [
            (row["label"], row["url"])
            for row in (res.data or [])
            if row.get("label") and row.get("url")
        ]
    except Exception:
        log.exception("Could not load buttons from Supabase; using defaults")

    return text, buttons


async def get_welcome_config():
    """Fetch text + buttons without blocking the bot."""
    return await asyncio.to_thread(_fetch_welcome_config)


def _save_member(user, chat_id: int, source: str) -> None:
    """Upsert the greeted user into the 'members' table (sync client)."""
    supabase.table("members").upsert(
        {
            "telegram_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "chat_id": chat_id,
            "source": source,
        },
        on_conflict="telegram_id,chat_id",
    ).execute()


async def log_member(user, chat_id: int, source: str) -> None:
    """Record the user in Supabase without ever crashing the bot."""
    try:
        await asyncio.to_thread(_save_member, user, chat_id, source)
        log.info("Saved %s (id=%s) to Supabase [%s]", user.first_name, user.id, source)
    except Exception:
        log.exception("Could not write member to Supabase")


# =============================================================
#  BOT LOGIC - you usually don't need to touch below here
# =============================================================


def _fix_url(url: str) -> str:
    """Forgive a missing https:// typed in the Table Editor."""
    url = url.strip()
    if not url.startswith(("http://", "https://", "tg://")):
        url = "https://" + url
    return url


def build_keyboard(buttons) -> InlineKeyboardMarkup | None:
    """Turn button rows into an inline keyboard (None = no buttons)."""
    rows = [[InlineKeyboardButton(label, url=_fix_url(url))] for label, url in buttons]
    return InlineKeyboardMarkup(rows) if rows else None


async def send_welcome(bot, chat_id: int, user) -> None:
    """Fetch the LATEST text and buttons from Supabase, then greet."""
    text, buttons = await get_welcome_config()
    keyboard = build_keyboard(buttons)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text.replace("{name}", user.mention_markdown()),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    except BadRequest:
        # The edited text likely has broken formatting (a stray * or _).
        # Send it as plain text so the greeting still goes out.
        log.warning("Markdown in welcome_text failed to parse; sent as plain text")
        await bot.send_message(
            chat_id=chat_id,
            text=text.replace("{name}", user.first_name),
            reply_markup=keyboard,
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs when a person opens the bot and taps Start."""
    user = update.effective_user
    await send_welcome(context.bot, update.effective_chat.id, user)
    await log_member(user, update.effective_chat.id, "start")


async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs when someone's membership in the group changes."""
    result = update.chat_member
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status

    # Only greet on a real join (left/kicked -> member), and never greet bots.
    just_joined = old_status in ("left", "kicked") and new_status == "member"
    if not just_joined or result.new_chat_member.user.is_bot:
        return

    user = result.new_chat_member.user
    await send_welcome(context.bot, result.chat.id, user)
    await log_member(user, result.chat.id, "group_join")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    # /start in a private chat
    app.add_handler(CommandHandler("start", start))
    # someone joining a group where the bot is an admin
    app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))

    log.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

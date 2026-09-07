"""
Telegram Welcome Bot
--------------------
Greets each person by name and shows tappable buttons.

Pipeline:  GitHub (code) -> Supabase (database) -> Railway (hosting) -> Telegram (bot)

Works two ways:
  - /start  -> greets a person in a private chat with the bot
  - join    -> greets a new member when they join your group

Every greeted person is also saved to a Supabase table called "members".

Configuration comes from ENVIRONMENT VARIABLES (never hardcode secrets):
  BOT_TOKEN      - from @BotFather
  SUPABASE_URL   - Supabase project URL        (Settings -> API)
  SUPABASE_KEY   - Supabase service_role key   (Settings -> API, keep secret)

For local testing: copy .env.example to .env and fill it in.
See README.md for the full GitHub -> Supabase -> Railway -> Telegram setup.
"""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from supabase import Client, create_client
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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
#  CONFIG - secrets come from the environment, edit text below
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

# The message body. {name} is replaced with the person's name.
WELCOME_TEXT = (
    "\U0001F44B *Welcome to our community, {name}!*\n\n"
    "To get started, please:\n\n"
    "1\uFE0F\u20E3 Read the pinned rules\n"
    "2\uFE0F\u20E3 Introduce yourself\n"
    "3\uFE0F\u20E3 Check out our resources\n"
)

# The tappable buttons. Each entry is one button on its own row.
# Format: ("Button label", "https://your-link")
BUTTONS = [
    ("\U0001F4D6 Read the Rules", "https://example.com/rules"),
    ("\U0001F4AC Join the Chat", "https://t.me/yourchat"),
    ("\U0001F310 Our Website", "https://example.com"),
]

# =============================================================
#  SUPABASE - every greeted person is upserted into "members"
# =============================================================

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


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


def build_keyboard() -> InlineKeyboardMarkup:
    """Turn the BUTTONS list into an inline keyboard."""
    rows = [[InlineKeyboardButton(label, url=url)] for label, url in BUTTONS]
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs when a person opens the bot and taps Start."""
    user = update.effective_user
    text = WELCOME_TEXT.format(name=user.mention_markdown())
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=build_keyboard()
    )
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
    text = WELCOME_TEXT.format(name=user.mention_markdown())
    await context.bot.send_message(
        chat_id=result.chat.id,
        text=text,
        parse_mode="Markdown",
        reply_markup=build_keyboard(),
    )
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

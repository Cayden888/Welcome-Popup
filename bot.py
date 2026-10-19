"""
Telegram Welcome Bot  (Supabase-editable, bilingual edition)
------------------------------------------------------------
Greets each person by name and shows tappable buttons.
The greeting posted in a GROUP disappears after WELCOME_DELETE_SECONDS.
The /start greeting in the bot's DM stays.

Pipeline:  GitHub (code) -> Supabase (database) -> Railway (hosting) -> Telegram (bot)

LANGUAGE PER GROUP
  - GROUP_LANG below maps each group ID to "zh" (Chinese) or "en" (English).
  - Groups not in the list use DEFAULT_LANG.
  - In the bot's DM (/start), the language follows the user's Telegram app
    language (Chinese app -> Chinese, anything else -> English).

SUPABASE TABLES
  - "bot_settings": one row per language
      * key = 'welcome_text_zh'  -> Chinese message
      * key = 'welcome_text_en'  -> English message
        (the old 'welcome_text' row still works as the English text)
      * Keep {name} where the member's name should appear.
      * *asterisks* make text bold.
  - "buttons": one row per button (sort_order, label, url, lang)
      * lang = 'zh' or 'en'  -> shown only in that language
      * lang empty           -> shown in BOTH languages
  - "members": everyone the bot has greeted (filled automatically).

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

# The group welcome disappears after this many seconds
WELCOME_DELETE_SECONDS = 300

# Which language each group gets. Add more groups here anytime.
GROUP_LANG = {
    -1004398257314: "zh",  # 中文群🎁
    -1003974610649: "en",  # BM Group (but english)🎁
}
DEFAULT_LANG = "en"  # for groups not listed above

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

DEFAULT_WELCOME_TEXT = {
    "en": (
        "\U0001F44B *Welcome to our community, {name}!*\n\n"
        "To get started, please:\n\n"
        "1\uFE0F\u20E3 Read the pinned rules\n"
        "2\uFE0F\u20E3 Introduce yourself\n"
        "3\uFE0F\u20E3 Check out our resources\n"
    ),
    "zh": (
        "\U0001F44B *欢迎加入我们的社群，{name}！*\n\n"
        "开始之前，请：\n\n"
        "1\uFE0F\u20E3 阅读置顶的群规\n"
        "2\uFE0F\u20E3 做个自我介绍\n"
        "3\uFE0F\u20E3 查看我们的资源\n"
    ),
}

DEFAULT_BUTTONS = {
    "en": [
        ("\U0001F4D6 Read the Rules", "https://example.com/rules"),
        ("\U0001F4AC Join the Chat", "https://t.me/yourchat"),
        ("\U0001F310 Our Website", "https://example.com"),
    ],
    "zh": [
        ("\U0001F4D6 阅读群规", "https://example.com/rules"),
        ("\U0001F4AC 加入聊天", "https://t.me/yourchat"),
        ("\U0001F310 官方网站", "https://example.com"),
    ],
}

# =============================================================
#  LANGUAGE
# =============================================================


def pick_lang(chat, user) -> str:
    """Group -> its mapped language. DM -> the user's Telegram app language."""
    if chat.type == "private":
        code = (getattr(user, "language_code", None) or "").lower()
        return "zh" if code.startswith("zh") else "en"
    return GROUP_LANG.get(chat.id, DEFAULT_LANG)


# =============================================================
#  SUPABASE
# =============================================================

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def _fetch_welcome_config(lang: str):
    """Read the welcome text and buttons for `lang` from Supabase (sync client)."""
    text = DEFAULT_WELCOME_TEXT.get(lang, DEFAULT_WELCOME_TEXT["en"])
    buttons = DEFAULT_BUTTONS.get(lang, DEFAULT_BUTTONS["en"])

    try:
        wanted = [f"welcome_text_{lang}"]
        if lang == "en":
            wanted.append("welcome_text")  # old single-language row still counts as English
        res = (
            supabase.table("bot_settings")
            .select("key, value")
            .in_("key", wanted)
            .execute()
        )
        found = {row["key"]: row.get("value") for row in (res.data or [])}
        for key in wanted:  # first match wins (language-specific row preferred)
            if found.get(key):
                # Accept both real line breaks and a typed "\n" in the Table Editor.
                text = found[key].replace("\\n", "\n")
                break
    except Exception:
        log.exception("Could not load welcome text (%s) from Supabase; using default", lang)

    try:
        res = supabase.table("buttons").select("*").order("sort_order").execute()
        # An empty table means "no buttons, on purpose" - that's allowed.
        # Rows with no lang show in every language.
        buttons = [
            (row["label"], row["url"])
            for row in (res.data or [])
            if row.get("label")
            and row.get("url")
            and (not row.get("lang") or str(row["lang"]).strip().lower() == lang)
        ]
    except Exception:
        log.exception("Could not load buttons from Supabase; using defaults")

    return text, buttons


async def get_welcome_config(lang: str):
    """Fetch text + buttons without blocking the bot."""
    return await asyncio.to_thread(_fetch_welcome_config, lang)


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


async def _delete_later(bot, chat_id: int, message_id: int, delay: int) -> None:
    """Delete a message after `delay` seconds (keeps the group clean)."""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        log.warning("Could not delete message %s in chat %s", message_id, chat_id)


async def send_welcome(bot, chat, user):
    """Fetch the LATEST text and buttons for this chat's language, then greet.
    Returns the sent message so callers can schedule the clean-up."""
    lang = pick_lang(chat, user)
    text, buttons = await get_welcome_config(lang)
    keyboard = build_keyboard(buttons)
    try:
        return await bot.send_message(
            chat_id=chat.id,
            text=text.replace("{name}", user.mention_markdown()),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    except BadRequest:
        # The edited text likely has broken formatting (a stray * or _).
        # Send it as plain text so the greeting still goes out.
        log.warning("Markdown in welcome text (%s) failed to parse; sent as plain text", lang)
        return await bot.send_message(
            chat_id=chat.id,
            text=text.replace("{name}", user.first_name),
            reply_markup=keyboard,
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs when a person opens the bot and taps Start."""
    user = update.effective_user
    chat = update.effective_chat
    msg = await send_welcome(context.bot, chat, user)
    # In the bot's DM the greeting stays; if /start happens in a group, clean it up.
    if chat.type != "private" and msg:
        context.application.create_task(
            _delete_later(context.bot, chat.id, msg.message_id, WELCOME_DELETE_SECONDS)
        )
    await log_member(user, chat.id, "start")


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
    msg = await send_welcome(context.bot, result.chat, user)
    # The group welcome deletes itself after WELCOME_DELETE_SECONDS
    if msg:
        context.application.create_task(
            _delete_later(context.bot, result.chat.id, msg.message_id, WELCOME_DELETE_SECONDS)
        )
    await log_member(user, result.chat.id, "group_join")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    # /start in a private chat
    app.add_handler(CommandHandler("start", start))
    # someone joining a group where the bot is an admin
    app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))

    log.info("Welcome Bot [bilingual] is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

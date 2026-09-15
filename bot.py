"""
Telegram Welcome Bot  (Supabase-editable edition)
-------------------------------------------------
Greets each person by name and shows tappable buttons.

Auto-delete rules (see AUTO-DELETE SETTINGS below):
  * Each group can have its OWN timer - list its ID in GROUP_DELETE_SECONDS.
    Groups not listed use DEFAULT_GROUP_DELETE_SECONDS.
  * The /start greeting in the bot's DM ALWAYS pops. It is removed after
    DM_DELETE_SECONDS, or kept forever if you set that to None.
  * NEW: when someone joins a group, the bot ALSO DMs them the same
    welcome via @WBF1Welcome_Bot. Telegram rule: a bot may only DM people
    who tapped Start on it at least once - everyone else is skipped
    quietly. Tip: add a button in Supabase pointing to
    https://t.me/WBF1Welcome_Bot so new members can reach the bot.
  * NEWER: turn ON "member approval" in the group/channel and the bot can
    DM EVERYONE. Telegram's one exception to the rule above: while a join
    request is pending, the bot IS allowed to message that person first.
    So the bot DMs the welcome, then approves them instantly
    (see AUTO_APPROVE_JOIN_REQUESTS).

Pipeline:  GitHub (code) -> Supabase (database) -> Railway (hosting) -> Telegram (bot)

The welcome text and the buttons live in Supabase, so you can change
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
import time

from dotenv import load_dotenv
from supabase import Client, create_client
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    Application,
    ChatJoinRequestHandler,
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
#  AUTO-DELETE SETTINGS - all times are in SECONDS
#  Cheat sheet: 60 = 1 min | 180 = 3 min | 300 = 5 min
# =============================================================

# Groups with their own timer. One line per group:
# group ID on the left, seconds on the right.
GROUP_DELETE_SECONDS = {
    -1003915223958: 300,  # this group: greeting disappears after 5 minutes
}

# Every group NOT listed above uses this timer:
DEFAULT_GROUP_DELETE_SECONDS = 300

# The bot's own DM (/start): the greeting always pops.
# A number  = it is removed after that many seconds.
# None      = it stays forever (write None without quotes).
DM_DELETE_SECONDS = 180  # 3 minutes

# When the group/channel has "member approval" turned on, the bot DMs the
# welcome to whoever taps "Request to Join", then lets them in right away.
# Set to False if you'd rather approve people yourself in Telegram.
AUTO_APPROVE_JOIN_REQUESTS = True

# =============================================================
#  COMMAND MENU - the list users see when they tap "Menu"
#  or type "/" in the chat.
#
#  TO ADD A COMMAND you only touch these two lists:
#    1) BOT_COMMANDS - what shows in the menu (name + short description)
#    2) TEXT_COMMANDS - what the bot replies when that command is tapped
#  /start is handled separately (it sends the full Supabase welcome), so
#  it does NOT need a line in TEXT_COMMANDS.
#
#  Command names must be lowercase, no spaces (a-z, 0-9, underscore).
# =============================================================

BOT_COMMANDS = [
    ("start", "Show the welcome message"),
    ("help", "What this bot can do"),
    ("join", "How to join / the links"),
    ("insta", "Our Instagram link"),
]

# Reply text for the simple commands. {name} becomes the person's name,
# and *asterisks* make text bold, same as the welcome. Each reply also
# shows your Supabase buttons underneath.
TEXT_COMMANDS = {
    "help": (
        "\u2139\uFE0F *Here's what I can do*\n\n"
        "\u2022 /start - see the welcome and the buttons again\n"
        "\u2022 /join - the links to get you in\n"
    ),
    "join": (
        "Tap a button below to get started, {name}! \U0001F447"
    ),
}

# Commands that show a LINK stored in Supabase, so you can change the link
# anytime without touching the code.
#   - "key"     : the row key to add in the bot_settings table
#   - "text"    : the message; {link} is replaced with the value from Supabase
#   - "default" : used only if Supabase is down or the row is empty
#
# TO ADD ANOTHER LINK COMMAND (e.g. /youtube):
#   1) add a line here (pick a key like "youtube_link")
#   2) add it to BOT_COMMANDS above so it shows in the menu
#   3) in Supabase -> bot_settings, add a row: key = youtube_link, value = the URL
LINK_COMMANDS = {
    "insta": {
        "key": "insta_link",
        "text": "\U0001F4F8 Follow us on Instagram:\n{link}",
        "default": "https://instagram.com/yourpage",
    },
}

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


def _fetch_setting(key: str, default: str = "") -> str:
    """Read one value from the bot_settings table by its key (sync client)."""
    try:
        res = (
            supabase.table("bot_settings")
            .select("value")
            .eq("key", key)
            .limit(1)
            .execute()
        )
        if res.data and res.data[0].get("value"):
            return res.data[0]["value"].strip()
    except Exception:
        log.exception("Could not load '%s' from Supabase; using default", key)
    return default


async def get_setting(key: str, default: str = "") -> str:
    """Fetch a single bot_settings value without blocking the bot."""
    return await asyncio.to_thread(_fetch_setting, key, default)


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


def _group_delete_delay(chat_id: int) -> int:
    """Which auto-delete timer applies to this group?"""
    return GROUP_DELETE_SECONDS.get(chat_id, DEFAULT_GROUP_DELETE_SECONDS)


# Remembers who was JUST welcomed by DM, so a join request followed by the
# "joined the group" event doesn't send the same person two identical DMs.
_recent_dms: dict[int, float] = {}


def _mark_dmed(user_id: int) -> None:
    now = time.time()
    _recent_dms[user_id] = now
    if len(_recent_dms) > 500:  # keep this little memory tidy
        for uid, stamp in list(_recent_dms.items()):
            if now - stamp > 120:
                del _recent_dms[uid]


def _just_dmed(user_id: int) -> bool:
    return time.time() - _recent_dms.get(user_id, 0) < 60


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
    """Delete a message after `delay` seconds (keeps the chat clean)."""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        log.warning("Could not delete message %s in chat %s", message_id, chat_id)


async def send_welcome(bot, chat_id: int, user):
    """Fetch the LATEST text and buttons from Supabase, then greet.
    Returns the sent message so callers can schedule the clean-up."""
    text, buttons = await get_welcome_config()
    keyboard = build_keyboard(buttons)
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text.replace("{name}", user.mention_markdown()),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    except BadRequest:
        # The edited text likely has broken formatting (a stray * or _).
        # Send it as plain text so the greeting still goes out.
        log.warning("Markdown in welcome_text failed to parse; sent as plain text")
        return await bot.send_message(
            chat_id=chat_id,
            text=text.replace("{name}", user.first_name),
            reply_markup=keyboard,
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs when a person opens the bot and taps Start."""
    user = update.effective_user
    chat = update.effective_chat
    msg = await send_welcome(context.bot, chat.id, user)

    if msg:
        if chat.type == "private":
            # The DM greeting always pops; remove it later only if a timer is set.
            if DM_DELETE_SECONDS is not None:
                context.application.create_task(
                    _delete_later(context.bot, chat.id, msg.message_id, DM_DELETE_SECONDS)
                )
        else:
            # /start typed inside a group follows that group's timer.
            context.application.create_task(
                _delete_later(
                    context.bot, chat.id, msg.message_id, _group_delete_delay(chat.id)
                )
            )

    await log_member(user, chat.id, "start")


async def text_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Answers any simple command listed in TEXT_COMMANDS (e.g. /help, /join).
    One handler serves them all - the reply text is looked up by name."""
    user = update.effective_user
    # update.message.text looks like "/help" or "/help@YourBot" - pull the name.
    raw = (update.message.text or "").lstrip("/").split()[0]
    cmd = raw.split("@")[0].lower()

    text = TEXT_COMMANDS.get(cmd)
    if not text:
        return  # not one of ours

    # Show the same Supabase buttons under the reply.
    _, buttons = await get_welcome_config()
    keyboard = build_keyboard(buttons)
    try:
        await update.message.reply_text(
            text.replace("{name}", user.mention_markdown()),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    except BadRequest:
        # A stray * or _ broke the formatting; send it plain so it still goes out.
        await update.message.reply_text(
            text.replace("{name}", user.first_name),
            reply_markup=keyboard,
        )


async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Answers a link command (e.g. /insta) with a URL pulled from Supabase,
    so the link can be changed in the dashboard without editing the code."""
    user = update.effective_user
    raw = (update.message.text or "").lstrip("/").split()[0]
    cmd = raw.split("@")[0].lower()

    conf = LINK_COMMANDS.get(cmd)
    if not conf:
        return  # not one of ours

    link = await get_setting(conf["key"], conf["default"])
    text = conf["text"].replace("{link}", link).replace("{name}", user.first_name)

    # A tappable button too, when the link looks usable.
    keyboard = build_keyboard([("Open", link)]) if link else None
    await update.message.reply_text(text, reply_markup=keyboard)


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

    # 1) Greet inside the group (deletes itself after that group's timer).
    #    Channels are skipped here - posting a public hello for every new
    #    subscriber would spam the channel feed. Channel members still get
    #    the DM below / via their join request.
    if result.chat.type != "channel":
        msg = await send_welcome(context.bot, result.chat.id, user)
        if msg:
            context.application.create_task(
                _delete_later(
                    context.bot, result.chat.id, msg.message_id, _group_delete_delay(result.chat.id)
                )
            )

    # 2) ALSO send the same welcome in the bot's DM (@WBF1Welcome_Bot).
    #    Telegram only allows this for people who tapped Start on the bot
    #    at least once OR who came in through a join request (handled in
    #    handle_join_request below). Everyone else is skipped quietly.
    if _just_dmed(user.id):
        log.info("%s already got the DM via their join request; not sending twice", user.first_name)
    else:
        try:
            dm = await send_welcome(context.bot, user.id, user)
            _mark_dmed(user.id)
            if dm and DM_DELETE_SECONDS is not None:
                context.application.create_task(
                    _delete_later(context.bot, user.id, dm.message_id, DM_DELETE_SECONDS)
                )
            log.info("Sent welcome DM to %s (id=%s)", user.first_name, user.id)
        except Forbidden:
            log.info(
                "%s (id=%s) hasn't started the bot yet, so Telegram blocks the DM",
                user.first_name,
                user.id,
            )
        except Exception:
            log.exception("Could not send welcome DM")

    await log_member(user, result.chat.id, "group_join")


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs when someone taps "Request to Join" (member approval is ON).

    This is Telegram's ONE exception to the no-DM-ing-strangers rule:
    while a join request is pending, the bot IS allowed to message that
    person first. So we DM the welcome, then approve them straight away -
    to the member it feels instant."""
    req = update.chat_join_request
    user = req.from_user
    if user.is_bot:
        return

    # Telegram hands us a private-chat id we may use while the request is pending.
    dm_chat_id = getattr(req, "user_chat_id", None) or user.id

    # 1) DM the welcome while Telegram still allows it.
    try:
        dm = await send_welcome(context.bot, dm_chat_id, user)
        _mark_dmed(user.id)
        if dm and DM_DELETE_SECONDS is not None:
            context.application.create_task(
                _delete_later(context.bot, dm_chat_id, dm.message_id, DM_DELETE_SECONDS)
            )
        log.info("DM'd the welcome to join-requester %s (id=%s)", user.first_name, user.id)
    except Exception:
        log.exception("Could not DM the join-requester")

    # 2) Open the door. Needs the bot to have the "Invite Users via Link"
    #    admin right. The normal in-group greeting then fires on its own
    #    through welcome_new_member.
    if AUTO_APPROVE_JOIN_REQUESTS:
        try:
            await req.approve()
        except Exception:
            log.exception("Could not approve the join request")

    await log_member(user, req.chat.id, "join_request")


async def _set_commands(app) -> None:
    """Push the command list to Telegram so it shows in the Menu / '/' popup."""
    try:
        await app.bot.set_my_commands([BotCommand(name, desc) for name, desc in BOT_COMMANDS])
        log.info("Command menu registered: %s", ", ".join(f"/{c}" for c, _ in BOT_COMMANDS))
    except Exception:
        log.exception("Could not set the command menu")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).post_init(_set_commands).build()

    # /start in a private chat
    app.add_handler(CommandHandler("start", start))
    # every simple command from TEXT_COMMANDS (/help, /join, ...) -> one handler
    for name in TEXT_COMMANDS:
        app.add_handler(CommandHandler(name, text_command))
    # every link command from LINK_COMMANDS (/insta, ...) -> one handler
    for name in LINK_COMMANDS:
        app.add_handler(CommandHandler(name, link_command))
    # someone joining a group where the bot is an admin
    app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))
    # someone tapping "Request to Join" (when member approval is turned on)
    app.add_handler(ChatJoinRequestHandler(handle_join_request))

    log.info("Welcome Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

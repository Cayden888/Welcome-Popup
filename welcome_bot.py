import asyncio
import logging
import os
import re
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMemberUpdated
from telegram.ext import (
    ApplicationBuilder, ChatMemberHandler, CommandHandler,
    MessageHandler, filters, ContextTypes, CallbackQueryHandler
)
from telegram.constants import ChatMemberStatus

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# ─── Config - Remember to add bot to both channel and group as admin to utilize this ──────────────────────────────────────────────────
BOT_TOKEN      = os.getenv("BOT_TOKEN")
DRAW_GROUP_ID  = int(os.getenv("DRAW_GROUP_ID", "-1003974610649"))
ADMIN_IDS      = [8875069703, 8829227838]
BOT_USERNAME   = "WBF1Welcome_Bot"  # no "@" here — this goes inside t.me/... links
SUPABASE_URL   = os.getenv("SUPABASE_URL", "https://puudkkacpszccjxciscr.supabase.co")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY")

def get_headers():
    key = os.getenv("SUPABASE_KEY") or SUPABASE_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

# ─── Messages ────────────────────────────────────────────────
WELCOME = {
    "en": "👋 Welcome, {name}! We run regular Lucky Draw Giveaways here. *Register your Winbox UID* to join! 🎁",
    "bm": "👋 Selamat datang, {name}! Kami kerap adakan Cabutan Bertuah di sini. *Daftar Winbox UID* anda untuk menyertai! 🎁",
    "zh": "👋 欢迎，{name}！我们定期举办幸运抽奖。*注册 Winbox UID* 即可参与！🎁",
}
DM_REGISTER = {
    "en": "👋 Hi {name}!\n\nPlease send your *Winbox UID* now.\n\n✅ Must start with a letter\n✅ Letters and numbers only\n✅ 6–15 characters\n\nExample: `abcd1234`",
    "bm": "👋 Hi {name}!\n\nSila hantar *Winbox UID* anda sekarang.\n\n✅ Mesti bermula dengan huruf\n✅ Huruf dan nombor sahaja\n✅ 6–15 karakter\n\nContoh: `abcd1234`",
    "zh": "👋 你好，{name}！\n\n请发送你的 *Winbox UID*。\n\n✅ 必须以字母开头\n✅ 只能包含字母和数字\n✅ 长度 6-15 位\n\n例子：`abcd1234`",
}
DM_START = {
    "en": "👋 Hi {name}! Welcome to WB FIFA Lucky Draw Bot.\n\nSend /register to register your Winbox UID.",
    "bm": "👋 Hi {name}! Selamat datang ke WB FIFA Lucky Draw Bot.\n\nHantar /register untuk daftar Winbox UID anda.",
    "zh": "👋 你好，{name}！欢迎使用 WB FIFA 幸运抽奖 Bot。\n\n发送 /register 以注册你的 Winbox UID。",
}
NO_UID_MSG = {
    "en": "Do you have a Winbox UID?",
    "bm": "Adakah anda mempunyai Winbox UID?",
    "zh": "你有 Winbox UID 吗？",
}

UID_INVALID = {
    "en": "❌ Invalid UID format.\n\n✅ Must start with a letter\n✅ Letters and numbers only\n✅ 6–15 characters\n\nExample: `abcd1234`\n\nPlease try again:",
    "bm": "❌ Format UID tidak sah.\n\n✅ Mesti bermula dengan huruf\n✅ Huruf dan nombor sahaja\n✅ 6–15 karakter\n\nContoh: `abcd1234`\n\nSila cuba lagi:",
    "zh": "❌ UID 格式不正确。\n\n✅ 必须以字母开头\n✅ 只能包含字母和数字\n✅ 长度 6-15 位\n\n例子：`abcd1234`\n\n请重新输入：",
}
UID_CONFIRM = {
    "en": "Please confirm your Winbox UID:\n\n`{uid}`\n\nIs this correct?",
    "bm": "Sila sahkan Winbox UID anda:\n\n`{uid}`\n\nAdakah ini betul?",
    "zh": "请确认你的 Winbox UID：\n\n`{uid}`\n\n是否正确？",
}
UID_REENTER = {
    "en": "No problem! Please send your Winbox UID again:",
    "bm": "Tiada masalah! Sila hantar semula Winbox UID anda:",
    "zh": "没关系！请重新输入你的 Winbox UID：",
}
UID_DUPLICATE = {
    "en": "⚠️ You have already registered. Please wait for admin approval.",
    "bm": "⚠️ Anda telah mendaftar. Sila tunggu kelulusan admin.",
    "zh": "⚠️ 你已经注册过了，请等待管理员审核。",
}
UID_PENDING = {
    "en": "✅ Registration submitted! Your UID is under review.\n\nWe will notify you once approved. 🙏",
    "bm": "✅ Pendaftaran dihantar! UID anda sedang disemak.\n\nKami akan maklumkan setelah diluluskan. 🙏",
    "zh": "✅ 注册已提交！你的 UID 正在审核中。\n\n审核通过后我们会通知你。🙏",
}
APPROVED_MSG = {
    "en": "🎉 Congratulations {name}! Your registration is *approved*.\n\nYou can now use /join in the draw group to join giveaways!",
    "bm": "🎉 Tahniah {name}! Pendaftaran anda telah *diluluskan*.\n\nAnda boleh gunakan /join dalam kumpulan cabutan untuk menyertai!",
    "zh": "🎉 恭喜 {name}！你的注册已*通过审核*。\n\n现在可以在抽奖群发送 /join 参加抽奖！",
}
REJECTED_MSG = {
    "en": "❌ Sorry {name}, your registration was *rejected*.\n\nPlease make sure your Winbox UID is registered on our official website before submitting again.",
    "bm": "❌ Maaf {name}, pendaftaran anda telah *ditolak*.\n\nSila pastikan Winbox UID anda telah didaftarkan di laman web rasmi kami sebelum menghantar semula.",
    "zh": "❌ 抱歉 {name}，你的注册未通过审核。\n\n请确保你的 Winbox UID 已在我们的官方网站注册后再重新提交。",
}

APPROVED_KEYBOARD = InlineKeyboardMarkup([[
    InlineKeyboardButton("🎯 Join Draw Group", url="https://t.me/+o7p-IDZlRzlhMzFl"),
]])

REJECTED_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("📝 Register UID", url="https://pixelharvia.com/r/9u9GRvr")],
    [InlineKeyboardButton("🔄 Resubmit", url=f"https://t.me/{BOT_USERNAME}?start=register")],
])

# ─── Helpers ─────────────────────────────────────────────────
def get_lang(user):
    lang = getattr(user, "language_code", None) or "en"
    if lang.startswith("ms"): return "bm"
    if lang.startswith("zh"): return "zh"
    return "en"

def is_valid_uid(uid: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9]{5,14}$", uid.strip()))

# ─── Auto-delete helper (messages self-destruct) ─────────────
AUTO_DELETE_SECONDS = 30

async def _delete_later(bot, chat_id, message_ids, delay):
    await asyncio.sleep(delay)
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass  # already deleted, or missing delete permission

async def _dm_copy(bot, user_id, text, kwargs):
    try:
        await bot.send_message(chat_id=user_id, text=text, **kwargs)
    except Exception:
        pass  # user has never started the bot — Telegram blocks the DM

async def reply_temp(update, context, text, delay=AUTO_DELETE_SECONDS, delete_command=True, dm_copy=True, **kwargs):
    """Reply in the group (auto-deletes after `delay`s) AND send a permanent copy to the user's DM."""
    msg = await update.message.reply_text(text, **kwargs)
    ids = [msg.message_id]
    if delete_command and update.effective_chat.type != "private":
        ids.append(update.message.message_id)
    context.application.create_task(
        _delete_later(context.bot, update.effective_chat.id, ids, delay)
    )
    # Permanent DM copy — fired in the background so it NEVER slows the group reply
    if dm_copy and update.effective_chat.type != "private":
        context.application.create_task(
            _dm_copy(context.bot, update.effective_user.id, text, kwargs)
        )
    return msg

async def _dm_start_welcome(bot, user_id, lang, name):
    """Send the /start welcome (Register Now / Channel / Draw Group buttons) to the user's DM."""
    try:
        text = await get_msg("dm_start", lang, DM_START[lang], name=name)
        await bot.send_message(
            chat_id=user_id, text=text,
            parse_mode="Markdown", reply_markup=start_keyboard(),
        )
    except Exception:
        pass  # user has never started the bot — Telegram blocks the DM

async def supabase_get(table, params):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=get_headers(), params=params)
        return r.json()

async def supabase_insert(table, data):
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{SUPABASE_URL}/rest/v1/{table}",
                              headers={**get_headers(), "Prefer": "return=representation"}, json=data)
        return r.json()

async def supabase_delete(table, match_params):
    async with httpx.AsyncClient() as client:
        await client.delete(f"{SUPABASE_URL}/rest/v1/{table}",
                            headers=get_headers(), params=match_params)

async def supabase_update(table, match_params, data):
    async with httpx.AsyncClient() as client:
        r = await client.patch(f"{SUPABASE_URL}/rest/v1/{table}",
                               headers={**get_headers(), "Prefer": "return=representation"},
                               params=match_params, json=data)
        return r.json()

# ─── Get message from Supabase ──────────────────────────────
async def get_msg(key: str, lang: str, fallback: str, **kwargs) -> str:
    try:
        result = await supabase_get("messages", {"key": f"eq.{key}", "lang": f"eq.{lang}"})
        if result:
            return result[0]["text"].format(**kwargs) if kwargs else result[0]["text"]
    except Exception:
        pass
    return fallback.format(**kwargs) if kwargs else fallback

# ─── Keyboards ───────────────────────────────────────────────
def welcome_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📝 Register Now", url=f"https://t.me/{BOT_USERNAME}?start=register"),
        InlineKeyboardButton("📢 Channel", url="https://t.me/WBExtraBonus88"),
    ]])

def start_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Register Now", callback_data="start_register")],
        [
            InlineKeyboardButton("📢 Channel", url="https://t.me/WBExtraBonus88"),
            InlineKeyboardButton("🎯 Draw Group", url="https://t.me/+o7p-IDZlRzlhMzFl"),
        ],
    ])

def no_uid_keyboard(lang):
    have = {"en": "✅ Yes, I have UID", "bm": "✅ Ya, saya ada UID", "zh": "✅ 有，我有 UID"}
    no   = {"en": "❌ No, register now", "bm": "❌ Belum, daftar sekarang", "zh": "❌ 没有，去注册"}
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(have[lang], callback_data="has_uid")],
        [InlineKeyboardButton(no[lang], url="https://pixelharvia.com/r/9u9GRvr")],
    ])

def confirm_keyboard(lang):
    yes = {"en": "✅ Yes, confirm", "bm": "✅ Ya, sahkan", "zh": "✅ 确认"}
    no  = {"en": "❌ No, re-enter", "bm": "❌ Tidak, masuk semula", "zh": "❌ 重新输入"}
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(yes[lang], callback_data="uid_confirm"),
        InlineKeyboardButton(no[lang],  callback_data="uid_reenter"),
    ]])

def admin_keyboard(reg_id, user_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve:{reg_id}:{user_id}"),
        InlineKeyboardButton("❌ Reject",  callback_data=f"reject:{reg_id}:{user_id}"),
    ]])

# ─── Group welcome ───────────────────────────────────────────
def member_just_joined(update: ChatMemberUpdated) -> bool:
    old = update.old_chat_member.status
    new = update.new_chat_member.status
    return (old in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED) and
            new in (ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED))

async def greet_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if not member_just_joined(result): return
    user = result.new_chat_member.user
    if result.chat.id != DRAW_GROUP_ID or user.is_bot: return
    name = user.first_name or user.username or "Friend"
    lang = get_lang(user)
    # Permanent welcome — sent with plain send_message, so it is NEVER auto-deleted
    msg = await get_msg("welcome", lang, WELCOME[lang], name=name)
    await context.bot.send_message(
        chat_id=DRAW_GROUP_ID,
        text=msg,
        parse_mode="Markdown",
        reply_markup=welcome_keyboard(),
    )

# ─── /start ──────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name or "Friend"
    lang = get_lang(user)
    if context.args and context.args[0] == "register":
        # Check existing registration status
        existing = await supabase_get("registrations", {"telegram_id": f"eq.{user.id}"})
        if existing:
            status = existing[0].get("status", "")
            if status == "approved":
                name = user.first_name or "Friend"
                msg = await get_msg("approved", lang, APPROVED_MSG[lang], name=name)
                await update.message.reply_text(
                    msg,
                    parse_mode="Markdown",
                    reply_markup=APPROVED_KEYBOARD
                )
                await update.message.reply_text(UID_DUPLICATE[lang], parse_mode="Markdown")
                return
            # Rejected — allow re-register
            await supabase_delete("registrations", {"telegram_id": f"eq.{user.id}"})
        context.user_data["lang"] = lang
        context.user_data["awaiting_uid"] = False
        await update.message.reply_text(
            NO_UID_MSG[lang],
            reply_markup=no_uid_keyboard(lang)
        )
    else:
        msg = await get_msg("dm_start", lang, DM_START[lang], name=name)
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=start_keyboard())

# ─── /register ───────────────────────────────────────────────
async def register_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_lang(user)

    # Only allow in DM
    if update.effective_chat.type != "private":
        name = user.first_name or "Friend"
        await reply_temp(
            update, context,
            "📩 Please DM me to register: @WBExtraBonus88_bot",
            parse_mode="Markdown",
            dm_copy=False,
        )
        context.application.create_task(
            _dm_start_welcome(context.bot, user.id, lang, name)
        )
        return
    existing = await supabase_get("registrations", {"telegram_id": f"eq.{user.id}"})
    if existing:
        status = existing[0].get("status", "")
        if status == "approved":
            name = user.first_name or "Friend"
            msg = await get_msg("approved", lang, APPROVED_MSG[lang], name=name)
            await update.message.reply_text(
                msg,
                parse_mode="Markdown",
                reply_markup=APPROVED_KEYBOARD
            )
            return
        elif status == "pending":
            await update.message.reply_text(UID_DUPLICATE[lang], parse_mode="Markdown")
            return
        # Rejected — delete and allow re-register
        await supabase_delete("registrations", {"telegram_id": f"eq.{user.id}"})
    context.user_data["lang"] = lang
    context.user_data["awaiting_uid"] = False
    await update.message.reply_text(
        NO_UID_MSG[lang],
        reply_markup=no_uid_keyboard(lang)
    )


# ─── Receive UID ─────────────────────────────────────────────
async def receive_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    if not context.user_data.get("awaiting_uid"): return

    user = update.effective_user
    lang = context.user_data.get("lang") or get_lang(user)
    uid  = update.message.text.strip()

    if not is_valid_uid(uid):
        await update.message.reply_text(UID_INVALID[lang], parse_mode="Markdown")
        return

    # Check duplicate
    existing = await supabase_get("registrations", {"telegram_id": f"eq.{user.id}"})
    if existing:
        status = existing[0].get("status", "")
        if status in ("pending", "approved"):
            await update.message.reply_text(UID_DUPLICATE[lang], parse_mode="Markdown")
            return
        # Rejected users can re-register — delete old record first
        await supabase_delete("registrations", {"telegram_id": f"eq.{user.id}"})

    # Store UID temporarily, ask for confirmation
    context.user_data["pending_uid"] = uid.upper()
    context.user_data["awaiting_uid"] = False
    context.user_data["awaiting_confirm"] = True

    await update.message.reply_text(
        UID_CONFIRM[lang].format(uid=uid.upper()),
        parse_mode="Markdown",
        reply_markup=confirm_keyboard(lang),
    )

# ─── Start Register callback ─────────────────────────────────
async def handle_start_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    lang = get_lang(user)

    # Check existing registration
    existing = await supabase_get("registrations", {"telegram_id": f"eq.{user.id}"})
    if existing:
        status = existing[0].get("status", "")
        if status == "approved":
            name = user.first_name or "Friend"
            msg = await get_msg("approved", lang, APPROVED_MSG[lang], name=name)
            await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=APPROVED_KEYBOARD)
            return
        elif status == "pending":
            await query.edit_message_text(UID_DUPLICATE[lang], parse_mode="Markdown")
            return
        await supabase_delete("registrations", {"telegram_id": f"eq.{user.id}"})

    context.user_data["lang"] = lang
    context.user_data["awaiting_uid"] = False
    await query.edit_message_text(NO_UID_MSG[lang], reply_markup=no_uid_keyboard(lang))

# ─── Has UID callback ────────────────────────────────────────
async def handle_has_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user  = query.from_user
    lang  = context.user_data.get("lang") or get_lang(user)
    name  = user.first_name or "Friend"
    context.user_data["awaiting_uid"] = True
    msg = await get_msg("dm_register", lang, DM_REGISTER[lang], name=name)
    await query.edit_message_text(msg, parse_mode="Markdown")

# ─── Confirmation callback ───────────────────────────────────
async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    lang = context.user_data.get("lang") or get_lang(user)

    if query.data == "uid_reenter":
        context.user_data["awaiting_uid"] = True
        context.user_data["awaiting_confirm"] = False
        context.user_data["pending_uid"] = None
        await query.edit_message_text(UID_REENTER[lang], parse_mode="Markdown")
        return

    # Confirmed — save to Supabase
    uid = context.user_data.get("pending_uid")
    if not uid:
        return

    result = await supabase_insert("registrations", {
        "telegram_id":   user.id,
        "telegram_name": user.first_name or "",
        "username":      user.username or "",
        "winbox_uid":    uid,
        "status":        "pending",
    })
    reg_id = result[0]["id"] if result and isinstance(result, list) else "?"

    context.user_data["awaiting_confirm"] = False
    context.user_data["pending_uid"] = None

    pending_msg = await get_msg("uid_pending", lang, UID_PENDING[lang])
    await query.edit_message_text(pending_msg, parse_mode="Markdown")

    # Notify admins
    name  = user.first_name or user.username or "Unknown"
    admin_text = (
        f"📋 *New Registration*\n\n"
        f"👤 Name: {name}\n"
        f"🆔 Telegram ID: `{user.id}`\n"
        f"🎮 Winbox UID: `{uid}`"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id, text=admin_text,
                parse_mode="Markdown", reply_markup=admin_keyboard(reg_id, user.id),
            )
        except Exception as e:
            logging.error(f"Failed to notify admin {admin_id}: {e}")

# ─── Admin Approve / Reject ───────────────────────────────────
async def handle_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("Not authorized.", show_alert=True)
        return
    await query.answer()

    action, reg_id, user_id = query.data.split(":")
    user_id = int(user_id)
    new_status = "approved" if action == "approve" else "rejected"

    await supabase_update("registrations", {"id": f"eq.{reg_id}"}, {"status": new_status})

    try:
        reg  = await supabase_get("registrations", {"id": f"eq.{reg_id}"})
        name = reg[0]["telegram_name"] if reg else "Friend"
        lang = "en"  # default, safe fallback
        if action == "approve":
            msg = await get_msg("approved", lang, APPROVED_MSG[lang], name=name)
        else:
            msg = await get_msg("rejected", lang, REJECTED_MSG[lang], name=name)
        if action == "approve":
            kwargs = {"reply_markup": APPROVED_KEYBOARD}
        else:
            kwargs = {"reply_markup": REJECTED_KEYBOARD}
        await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown", **kwargs)
        logging.info(f"Notified user {user_id} of {action}")
    except Exception as e:
        logging.error(f"Failed to notify user {user_id}: {e}")

    status_text = "✅ Approved" if action == "approve" else "❌ Rejected"
    await query.edit_message_text(
        query.message.text + f"\n\n*{status_text}* by {query.from_user.first_name}",
        parse_mode="Markdown", reply_markup=None
    )

# ─── Admin preview ───────────────────────────────────────────
async def preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    name = update.effective_user.first_name or "Ahmad"
    msg = await get_msg("welcome", "en", WELCOME["en"], name=name)
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=welcome_keyboard())

# ═══════════════════════════════════════════════════════════════
# GIVEAWAY SECTION
# ═══════════════════════════════════════════════════════════════

CHANNEL_USERNAME = "WBExtraBonus88"

# ─── Giveaway Messages ───────────────────────────────────────
JOIN_NO_GIVEAWAY = {
    "en": "⚠️ No active giveaway at the moment. Stay tuned!",
    "bm": "⚠️ Tiada cabutan bertuah aktif buat masa ini. Nantikan!",
    "zh": "⚠️ 目前没有进行中的抽奖，请继续关注！",
}
JOIN_NOT_APPROVED = {
    "en": "❌ You need to *register* before joining a giveaway.\n\nSend /register to get started.",
    "bm": "❌ Anda perlu *mendaftar* sebelum menyertai cabutan.\n\nHantar /register untuk memulakan.",
    "zh": "❌ 你需要先*注册*才能参加抽奖。\n\n发送 /register 开始注册。",
}
JOIN_NOT_FOLLOWING = {
    "en": "❌ You need to *follow our channel* before joining.\n\nJoin the channel then try again!",
    "bm": "❌ Anda perlu *ikuti saluran kami* sebelum menyertai.\n\nSertai saluran dahulu kemudian cuba lagi!",
    "zh": "❌ 你需要先*关注我们的频道*才能参加。\n\n加入频道后再试一次！",
}
JOIN_ALREADY = {
    "en": "✅ You have already joined this giveaway! Good luck! 🍀",
    "bm": "✅ Anda telah menyertai cabutan ini! Semoga bernasib baik! 🍀",
    "zh": "✅ 你已经参加了这次抽奖！祝你好运！🍀",
}
JOIN_SUCCESS = {
    "en": "🎉 You're in! Good luck, {name}! 🍀",
    "bm": "🎉 Anda telah berjaya menyertai! Semoga bernasib baik, {name}! 🍀",
    "zh": "🎉 报名成功！祝你好运，{name}！🍀",
}
GIVEAWAY_STARTED = {
    "en": "🎁 *Giveaway Started!*\n\n{title}\n\nSend /join in this group to participate!\n\n✅ Must be registered & approved\n✅ Must follow @WBExtraBonus88",
    "bm": "🎁 *Cabutan Bertuah Bermula!*\n\n{title}\n\nHantar /join dalam kumpulan ini untuk menyertai!\n\n✅ Mesti berdaftar & diluluskan\n✅ Mesti ikuti @WBExtraBonus88",
    "zh": "🎁 *抽奖开始！*\n\n{title}\n\n在此群发送 /join 参与！\n\n✅ 必须已注册并通过审核\n✅ 必须关注 @WBExtraBonus88",
}
GIVEAWAY_ENDED = "🔒 *Registration Closed!*\n\n*{count}* participants have joined.\n\nThe live draw is happening now! 🎉"

# ─── Giveaway Keyboards ──────────────────────────────────────
def channel_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📢 Follow Channel", url="https://t.me/WBExtraBonus88"),
    ]])

# ─── Giveaway Helpers ────────────────────────────────────────
async def get_active_giveaway():
    result = await supabase_get("giveaways", {"is_active": "eq.true", "limit": "1"})
    return result[0] if result else None

async def is_approved(telegram_id):
    result = await supabase_get("registrations", {
        "telegram_id": f"eq.{telegram_id}",
        "status": "eq.approved"
    })
    return bool(result)

async def is_following_channel(bot, telegram_id):
    try:
        member = await bot.get_chat_member(f"@{CHANNEL_USERNAME}", telegram_id)
        return member.status not in ("left", "kicked")
    except Exception:
        return False

async def already_joined(giveaway_id, telegram_id):
    result = await supabase_get("participants", {
        "giveaway_id": f"eq.{giveaway_id}",
        "telegram_id": f"eq.{telegram_id}"
    })
    return bool(result)

# ─── /join ───────────────────────────────────────────────────
async def join_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != DRAW_GROUP_ID:
        return

    user = update.effective_user
    lang = get_lang(user)
    name = user.first_name or "Friend"

    # Check active giveaway
    giveaway = await get_active_giveaway()
    if not giveaway:
        await reply_temp(update, context, JOIN_NO_GIVEAWAY[lang], parse_mode="Markdown")
        return

    # Check approved
    if not await is_approved(user.id):
        # Group: short redirect (auto-deletes). Their bot DM: full /start welcome + buttons.
        await reply_temp(
            update, context,
            "📩 Please DM me to register first: @WBF1Welcome_Bot",
            dm_copy=False,
        )
        context.application.create_task(
            _dm_start_welcome(context.bot, user.id, lang, name)
        )
        return

    # Check following channel
    if not await is_following_channel(context.bot, user.id):
        await reply_temp(
            update, context,
            JOIN_NOT_FOLLOWING[lang],
            parse_mode="Markdown",
            reply_markup=channel_keyboard()
        )
        return

    # Check already joined
    if await already_joined(giveaway["id"], user.id):
        await reply_temp(update, context, JOIN_ALREADY[lang], parse_mode="Markdown")
        return

    # Get UID from registrations
    reg = await supabase_get("registrations", {"telegram_id": f"eq.{user.id}"})
    winbox_uid = reg[0]["winbox_uid"] if reg else ""

    # Save participant
    await supabase_insert("participants", {
        "giveaway_id":   giveaway["id"],
        "telegram_id":   user.id,
        "telegram_name": name,
        "winbox_uid":    winbox_uid,
    })

    success_msg = await get_msg("join_success", lang, JOIN_SUCCESS[lang], name=name)
    await reply_temp(update, context, success_msg, parse_mode="Markdown")

# ─── /startgiveaway [title] ──────────────────────────────────
async def start_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    # End any existing active giveaway first
    await supabase_update("giveaways", {"is_active": "eq.true"}, {"is_active": False})

    title = " ".join(context.args) if context.args else "Lucky Draw Giveaway"
    result = await supabase_insert("giveaways", {"title": title, "is_active": True})
    if not result:
        await update.message.reply_text("❌ Failed to start giveaway.")
        return

    # Announce in group
    start_msg = await get_msg("giveaway_started", "en", GIVEAWAY_STARTED["en"], title=title)
    await context.bot.send_message(
        chat_id=DRAW_GROUP_ID,
        text=start_msg,
        parse_mode="Markdown",
    )
    await update.message.reply_text(f"✅ Giveaway started: *{title}*", parse_mode="Markdown")

# ─── /stopjoin ───────────────────────────────────────────────
async def stop_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    giveaway = await get_active_giveaway()
    if not giveaway:
        await update.message.reply_text("⚠️ No active giveaway.")
        return

    # Get participant count
    participants = await supabase_get("participants", {"giveaway_id": f"eq.{giveaway['id']}"})
    count = len(participants) if participants else 0

    # Close registration
    await supabase_update("giveaways", {"id": f"eq.{giveaway['id']}"}, {"is_active": False})

    # Announce in group
    closed_msg = await get_msg("giveaway_closed", "en", GIVEAWAY_ENDED, count=count)
    await context.bot.send_message(
        chat_id=DRAW_GROUP_ID,
        text=closed_msg,
        parse_mode="Markdown",
    )
    await update.message.reply_text(f"✅ Registration closed. Total participants: *{count}*", parse_mode="Markdown")

# ─── /participants ───────────────────────────────────────────
async def list_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    giveaway = await get_active_giveaway()
    if not giveaway:
        # Get last giveaway
        result = await supabase_get("giveaways", {"order": "id.desc", "limit": "1"})
        giveaway = result[0] if result else None

    if not giveaway:
        await update.message.reply_text("⚠️ No giveaway found.")
        return

    participants = await supabase_get("participants", {"giveaway_id": f"eq.{giveaway['id']}"})
    if not participants:
        await update.message.reply_text("No participants yet.")
        return

    lines = [f"📋 *{giveaway['title']}* — {len(participants)} participants\n"]
    for i, p in enumerate(participants, 1):
        lines.append(f"{i}. {p['telegram_name']} — `{p['winbox_uid']}`")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─── Main ────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True).build()
    app.add_handler(ChatMemberHandler(greet_new_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("register", register_cmd))
    app.add_handler(CommandHandler("preview",  preview))
    app.add_handler(CallbackQueryHandler(handle_start_register, pattern=r"^start_register$"))
    app.add_handler(CallbackQueryHandler(handle_has_uid,  pattern=r"^has_uid$"))
    app.add_handler(CallbackQueryHandler(handle_confirm,  pattern=r"^uid_(confirm|reenter)$"))
    app.add_handler(CallbackQueryHandler(handle_decision, pattern=r"^(approve|reject):"))
    app.add_handler(CommandHandler("join",           join_giveaway))
    app.add_handler(CommandHandler("startgiveaway",  start_giveaway))
    app.add_handler(CommandHandler("stopjoin",       stop_join))
    app.add_handler(CommandHandler("participants",   list_participants))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_uid))
    print("Welcome Bot is running...")
    app.run_polling(allowed_updates=["chat_member", "message", "callback_query"])

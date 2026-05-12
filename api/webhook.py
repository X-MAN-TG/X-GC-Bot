"""
⚡ 𝗫 𝗚𝗰 𝗠𝗮𝗻𝗴𝗲𝗿 𝗕𝗼𝘁

Commands:
  /cutie    — deleted account scanner + safe purge confirmation
  /xdemote  — admin rights manager with Telethon owner session

Uses:
  aiogram 3.x  — bot commands, messages, inline buttons
  Telethon     — full member scan + admin-right editing through owner string session
"""

import asyncio
import html
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import EditAdminRequest
from telethon.tl.types import ChatAdminRights, User

# ══════════════════════════════════════════════════════════════
#  CONFIG — Railway / environment variables
# ══════════════════════════════════════════════════════════════
REQUIRED_ENV = ("BOT_TOKEN", "SESSION_STRING", "API_ID", "API_HASH", "OWNER_ID")
missing = [key for key in REQUIRED_ENV if not os.getenv(key)]
if missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

BOT_TOKEN = os.environ["8641524225:AAEYoasz5AIYHAmjAWgoy3alS4iTja0XrrQ"]
SESSION_STRING = os.environ["1BVtsOLEBu5_1eBVh1BGSZzX9FMm3x9NhVcEU1MR7hRvq6ijVXoR7LAwEEjYEyTJYv4aaA0sFYLMCHKksC38ihGTYFN-U0PJ_sfameY-9zScKFgS88eKLuoza2TaYYb5iV5nzJDCkkBoMcfaONnzZ9tW22XXCw3gI5Jcx4BomDiItpdmlVm9aBaMcCGD62AliVNLqVcRrxqfHmdIfJUjTc8LGffUCgJhdsOhjP58vqH6CPYFr2EB-YkNBsGVi7e_c6mXlHYoo5rE5v6WVxos2coBJBby1ewWPxaoBg5BkU_IxpYIVwbEAxMJW02V3nZ2Sx0K0piSQ9mPFapf8iKOlH7hZR7BJd6E="]
API_ID = int(os.environ["34135858"])
API_HASH = os.environ["2653940ace7a0291e461b20f0fba8cd4"]
OWNER_ID = int(os.environ["6810553459"])
SCAN_CACHE_SECONDS = int(os.getenv("SCAN_CACHE_SECONDS", "90"))
KICK_DELAY_SECONDS = float(os.getenv("KICK_DELAY_SECONDS", "0.08"))
ADMIN_EDIT_DELAY_SECONDS = float(os.getenv("ADMIN_EDIT_DELAY_SECONDS", "0.35"))
ADMIN_CARDS_LIMIT = int(os.getenv("ADMIN_CARDS_LIMIT", "80"))

WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "xgc-manager-secret")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

# ══════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
#  CLIENTS / LOCKS / CACHE
# ══════════════════════════════════════════════════════════════
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
tele = TelegramClient(StringSession(SESSION_STRING), api_id=API_ID, api_hash=API_HASH)

scan_lock = asyncio.Lock()
admin_edit_lock = asyncio.Lock()
scan_cache: dict[int, tuple[float, tuple[int, list[User], list[User]]]] = {}

# ══════════════════════════════════════════════════════════════
#  BUTTON STYLE HELPER
#  Telegram standard inline keyboards do not expose real hex colours.
#  This helper keeps your requested primary/success/danger API and
#  renders colour intent with strong emoji labels.
# ══════════════════════════════════════════════════════════════
STYLE_ICON = {
    "primary": "🔵",
    "success": "🟢",
    "danger": "🔴",
    "warning": "🟠",
    "dark": "⚫",
}


def btn(text: str, callback_data: str, style: str = "primary") -> InlineKeyboardButton:
    icon = STYLE_ICON.get(style, STYLE_ICON["primary"])
    return InlineKeyboardButton(text=f"{icon} {text}", callback_data=callback_data)


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("☠️ Kick Ghosts", "kick_deleted_prepare", "danger"), btn("🔍 Ghost Info", "info_deleted", "primary")],
        [btn("🛡 Admin Rights", "show_xdemote", "success")],
        [btn("🔄 Refresh Stats", "refresh_stats", "primary")],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("⬅️ Back", "refresh_stats", "primary")],
    ])


def purge_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("✅ Confirm Purge", "kick_deleted_confirm", "primary"), btn("❌ Cancel", "refresh_stats", "danger")],
    ])


def admin_card_keyboard(admin_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("✅ Give Full Rights", f"grant_admin_{admin_id}", "success"), btn("🚫 Take All Rights", f"strip_admin_{admin_id}", "danger")],
        [btn("🔁 Re-scan Admins", "show_xdemote", "primary")],
    ])


def admin_done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("🔁 Re-scan Admins", "show_xdemote", "primary")],
        [btn("⬅️ Back", "refresh_stats", "primary")],
    ])


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


# ══════════════════════════════════════════════════════════════
#  VALID GROUP CHECK
# ══════════════════════════════════════════════════════════════
def valid_group(chat_id: int) -> bool:
    return str(chat_id).startswith("-100")


async def owner_only(cb: CallbackQuery) -> bool:
    if cb.from_user.id != OWNER_ID:
        await cb.answer("🚫 Not your panel.", show_alert=True)
        return False

    if not cb.message:
        return False

    if not valid_group(cb.message.chat.id):
        await cb.answer("❌ Invalid group.", show_alert=True)
        return False

    return True


async def caller_is_admin(chat_id: int, user_id: int) -> bool:
    member = await bot.get_chat_member(chat_id, user_id)
    return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)


async def bot_can_ban(chat_id: int) -> bool:
    me = await bot.get_me()
    member = await bot.get_chat_member(chat_id, me.id)
    return bool(getattr(member, "can_restrict_members", False))

# ══════════════════════════════════════════════════════════════
#  GHOST SCAN
# ══════════════════════════════════════════════════════════════
async def full_scan(chat_id: int, *, force: bool = False) -> tuple[int, list[User], list[User]]:
    now = time.time()
    cached = scan_cache.get(chat_id)
    if not force and cached and now - cached[0] <= SCAN_CACHE_SECONDS:
        return cached[1]

    async with scan_lock:
        cached = scan_cache.get(chat_id)
        if not force and cached and time.time() - cached[0] <= SCAN_CACHE_SECONDS:
            return cached[1]

        alive: list[User] = []
        deleted: list[User] = []
        async for user in tele.iter_participants(chat_id):
            if getattr(user, "deleted", False):
                deleted.append(user)
            else:
                alive.append(user)

        result = (len(alive) + len(deleted), alive, deleted)
        scan_cache[chat_id] = (time.time(), result)
        return result


async def build_stats_text(chat_id: int, *, force: bool = False) -> tuple[str, int, list[User]]:
    chat_info = await bot.get_chat(chat_id)
    admins = await bot.get_chat_administrators(chat_id)

    owner_name = "Unknown"
    for admin in admins:
        if admin.status == ChatMemberStatus.CREATOR:
            owner_name = admin.user.full_name or admin.user.username or "Unknown"
            break

    total, alive_list, deleted_list = await full_scan(chat_id, force=force)
    group_name = esc(chat_info.title or "This Group")
    group_handle = f"@{esc(chat_info.username)}" if chat_info.username else "Private Group"

    text = (
        "⚡  <b>𝗫 𝗚𝗰 𝗠𝗮𝗻𝗴𝗲𝗿 𝗕𝗼𝘁 — ONLINE</b>\n"
        "<blockquote>━━━━━━━━━━━━━━━━━━━━━━━━━</blockquote>\n\n"
        f"🏠  <b>Group</b>     »  <code>{group_name}</code>\n"
        f"🔗  <b>Handle</b>    »  {group_handle}\n"
        f"👑  <b>Owner</b>     »  <b>{esc(owner_name)}</b>\n\n"
        "<blockquote>📊  M E M B E R   B R E A K D O W N</blockquote>\n\n"
        f"👥  <b>Total Members</b>    ›  <code>{total}</code>\n"
        f"✅  <b>Alive Accounts</b>   ›  <code>{len(alive_list)}</code>\n"
        f"☠️  <b>Deleted Accounts</b> ›  <code>{len(deleted_list)}</code>\n\n"
        "<i>Pick your move, boss 👇</i>"
    )
    return text, len(deleted_list), deleted_list

# ══════════════════════════════════════════════════════════════
#  ADMIN RIGHTS REPORT
# ══════════════════════════════════════════════════════════════
ADMIN_RIGHT_FIELDS = [
    ("can_change_info", "Change Info"),
    ("can_delete_messages", "Delete Messages"),
    ("can_restrict_members", "Ban Users"),
    ("can_invite_users", "Invite Link"),
    ("can_pin_messages", "Pin Messages"),
    ("can_manage_topics", "Topics/Tags"),
    ("can_manage_video_chats", "Live Streams"),
    ("can_promote_members", "Add Admins"),
    ("can_post_stories", "Post Stories"),
    ("can_edit_stories", "Edit Stories"),
    ("can_delete_stories", "Delete Stories"),
]


@dataclass
class AdminRow:
    user_id: int
    name: str
    username: str
    status: str
    title: str
    score: int
    total: int
    editable: bool
    is_bot: bool


def admin_score(admin: Any) -> tuple[int, int]:
    score = 0
    for attr, _label in ADMIN_RIGHT_FIELDS:
        if bool(getattr(admin, attr, False)):
            score += 1
    return score, len(ADMIN_RIGHT_FIELDS)


def rights_bar(count: int, total: int) -> str:
    # Scale any total to a 10-block visual bar.
    filled = round((count / total) * 10) if total else 0
    filled = max(0, min(10, filled))
    return f"{'█' * filled}{'░' * (10 - filled)}  <code>{count}/{total}</code>"


def perm_emoji(count: int, total: int) -> str:
    ratio = count / total if total else 0
    if ratio >= 0.82:
        return "🟢"
    if ratio >= 0.55:
        return "🟡"
    if ratio >= 0.28:
        return "🟠"
    return "🔴"


async def get_admin_rows(chat_id: int) -> list[AdminRow]:
    admins = await bot.get_chat_administrators(chat_id)
    rows: list[AdminRow] = []

    for admin in admins:
        score, total = admin_score(admin)
        user = admin.user
        is_creator = admin.status == ChatMemberStatus.CREATOR
        is_owner = user.id == OWNER_ID
        is_bot = bool(user.is_bot)
        rows.append(AdminRow(
            user_id=user.id,
            name=user.full_name or user.username or str(user.id),
            username=f"@{user.username}" if user.username else "no username",
            status=str(admin.status),
            title=getattr(admin, "custom_title", None) or "Admin",
            score=total if is_creator else score,
            total=total,
            editable=not is_creator and not is_owner and not is_bot,
            is_bot=is_bot,
        ))

    rows.sort(key=lambda r: (not r.editable, -r.score, r.name.lower()))
    return rows


async def build_admin_report(chat_id: int) -> tuple[str, list[AdminRow]]:
    rows = await get_admin_rows(chat_id)
    editable = [r for r in rows if r.editable]
    full_rights = sum(1 for r in editable if r.score / r.total >= 0.82)
    partial_rights = sum(1 for r in editable if 0 < r.score / r.total < 0.82)
    no_rights = sum(1 for r in editable if r.score == 0)

    lines = []
    for i, r in enumerate(rows, 1):
        badge = "👑" if r.status == str(ChatMemberStatus.CREATOR) else ("🤖" if r.is_bot else "🛡")
        protected = "  <i>protected</i>" if not r.editable else ""
        emoji = "👑" if r.status == str(ChatMemberStatus.CREATOR) else perm_emoji(r.score, r.total)
        lines.append(
            f"{emoji}  <b>{i}. {esc(r.name)}</b>  {badge}{protected}\n"
            f"     ├  <i>{esc(r.username)}</i>   <code>{r.user_id}</code>\n"
            f"     ├  <b>Tag</b>  »  <code>{esc(r.title)}</code>\n"
            f"     └  {rights_bar(r.score, r.total)}"
        )

    body = "\n\n".join(lines) if lines else "<i>No admins found.</i>"
    text = (
        "👑  <b>𝗔𝗗𝗠𝗜𝗡   𝗥𝗜𝗚𝗛𝗧𝗦   𝗥𝗘𝗣𝗢𝗥𝗧</b>\n"
        "<blockquote>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</blockquote>\n\n"
        "<blockquote>"
        f"  🛡  Total Admins    ›  <code>{len(rows)}</code>\n"
        f"  🟢  Full Rights     ›  <code>{full_rights}</code>\n"
        f"  🟡  Partial Rights  ›  <code>{partial_rights}</code>\n"
        f"  🔴  No Rights       ›  <code>{no_rights}</code>\n"
        f"  🔒  Editable        ›  <code>{len(editable)}</code>"
        "</blockquote>\n\n"
        "<b>━━  A D M I N   L I S T  ━━</b>\n\n"
        f"{body}\n\n"
        "<blockquote><i>🟢 high rights  ·  🟡 medium  ·  🟠 low  ·  🔴 nearly none\n"
        "Each editable admin gets a control card below.</i></blockquote>"
    )
    return text, rows


def full_admin_rights() -> ChatAdminRights:
    return ChatAdminRights(
        change_info=True,
        delete_messages=True,
        ban_users=True,
        invite_users=True,
        pin_messages=True,
        add_admins=True,
        anonymous=False,
        manage_call=True,
        other=True,
        manage_topics=True,
        post_stories=True,
        edit_stories=True,
        delete_stories=True,
    )


def title_only_rights() -> ChatAdminRights:
    # other=True keeps the admin/title tag while visible permission toggles stay off.
    return ChatAdminRights(
        change_info=False,
        delete_messages=False,
        ban_users=False,
        invite_users=False,
        pin_messages=False,
        add_admins=False,
        anonymous=False,
        manage_call=False,
        other=True,
        manage_topics=False,
        post_stories=False,
        edit_stories=False,
        delete_stories=False,
    )


async def edit_single_admin(chat_id: int, admin_id: int, mode: str) -> tuple[bool, str]:
    rows = await get_admin_rows(chat_id)
    target = next((r for r in rows if r.user_id == admin_id), None)
    if not target:
        return False, "Admin not found anymore. Re-scan and try again."
    if not target.editable:
        return False, "This admin is protected, owner, creator, or bot. Skipped."

    rights = full_admin_rights() if mode == "full" else title_only_rights()
    entity = await tele.get_entity(chat_id)

    async with admin_edit_lock:
        try:
            await tele(EditAdminRequest(entity, admin_id, rights, rank=target.title or "Admin"))
            await asyncio.sleep(ADMIN_EDIT_DELAY_SECONDS)
            return True, target.name
        except Exception as e:
            log.warning("Admin edit failed for %s: %s", admin_id, e)
            return False, str(e)

# ══════════════════════════════════════════════════════════════
#  COMMANDS
# ══════════════════════════════════════════════════════════════
@dp.message(Command("cutie"))
async def cutie_command(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not valid_group(chat_id):
        await message.reply(
            "❌ This command only works in groups."
        )
        return
    if not await caller_is_admin(chat_id, user_id):
        await message.reply("⛔  <b>Permission Denied</b>\n<i>Only admins can summon me.</i>  🗿")
        return

    scanning_msg = await message.reply(
        "🔍  <b>Scanning all members via deep scan…</b>\n"
        "<i>Give me a sec, going through every account.</i>"
    )
    try:
        text, _, _ = await build_stats_text(chat_id, force=True)
        await scanning_msg.delete()
        await message.reply(text, reply_markup=main_keyboard())
    except Exception as e:
        log.exception("cutie scan error")
        await scanning_msg.edit_text(f"❌ <b>Scan failed:</b> <code>{esc(e)}</code>")


@dp.message(Command("xdemote"))
async def xdemote_command(message: Message):
    if not valid_group(message.chat.id):
        await message.reply(
            "❌ This command only works in groups."
        )
        return
    if message.from_user.id != OWNER_ID:
        await message.reply("🚫  <b>Owner panel only.</b>\n<i>This command can edit admin powers.</i>")
        return

    wait_msg = await message.reply(
        "🔍  <b>Fetching admin list via deep scan…</b>\n"
        "<i>Pulling rights data for all admins.</i>"
    )

    try:
        report_text, rows = await build_admin_report(message.chat.id)
        await wait_msg.delete()
        await message.reply(report_text)

        editable = [r for r in rows if r.editable][:ADMIN_CARDS_LIMIT]
        if not editable:
            await message.reply(
                "ℹ️  <b>No editable admins found.</b>\n"
                "<i>All admins are protected, creator, owner, or bots.</i>",
                reply_markup=admin_done_keyboard(),
            )
            return

        for r in editable:
            emoji = perm_emoji(r.score, r.total)
            card = (
                f"{emoji}  <b>{esc(r.name)}</b>\n"
                "<blockquote>"
                f"  🪪  <code>{r.user_id}</code>   <i>{esc(r.username)}</i>\n"
                f"  🏷  Tag          :  <code>{esc(r.title)}</code>\n"
                f"  🔑  Permissions  :  {rights_bar(r.score, r.total)}"
                "</blockquote>"
            )
            await message.reply(card, reply_markup=admin_card_keyboard(r.user_id))
            await asyncio.sleep(0.35)

    except Exception as e:
        log.exception("xdemote error")
        await wait_msg.edit_text(f"❌ <b>Failed:</b> <code>{esc(e)}</code>")

# ══════════════════════════════════════════════════════════════
#  CALLBACKS — MAIN / GHOSTS
# ══════════════════════════════════════════════════════════════
@dp.callback_query(F.data == "refresh_stats")
async def cb_refresh(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    await cb.answer("🔄 Refreshing…")
    try:
        text, _, _ = await build_stats_text(cb.message.chat.id, force=True)
        await cb.message.edit_text(text, reply_markup=main_keyboard())
    except Exception as e:
        await cb.answer(f"Error: {e}", show_alert=True)


@dp.callback_query(F.data == "info_deleted")
async def cb_info(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    await cb.answer("🔍 Fetching ghost list…")
    chat_id = cb.message.chat.id

    try:
        _, _, deleted_list = await full_scan(chat_id, force=True)
    except Exception as e:
        await cb.answer(f"Scan error: {e}", show_alert=True)
        return

    if not deleted_list:
        await cb.message.reply("✅  <b>No deleted accounts found!</b>\n<i>Group is clean 🧹</i>", reply_markup=back_keyboard())
        return

    lines = []
    for i, user in enumerate(deleted_list, 1):
        username = f"@{esc(user.username)}" if user.username else "<i>—</i>"
        name = ((user.first_name or "") + " " + (user.last_name or "")).strip() or "Deleted Account"
        lines.append(f"  <b>{i}.</b>  <code>{user.id}</code>   {username}\n         └─  <i>{esc(name)}</i>")

    chunks = [lines[i : i + 30] for i in range(0, len(lines), 30)]
    header = (
        "☠️  <b>DELETED ACCOUNT REPORT</b>\n"
        "<blockquote>━━━━━━━━━━━━━━━━━━━━━━━</blockquote>\n\n"
        f"<b>Total Ghosts :</b>  <code>{len(deleted_list)}</code>\n\n"
    )
    for idx, chunk in enumerate(chunks):
        msg_text = (header if idx == 0 else f"<b>☠️ Continued… ({idx + 1}/{len(chunks)})</b>\n\n") + "\n".join(chunk)
        await cb.message.reply(msg_text, reply_markup=back_keyboard() if idx == len(chunks) - 1 else None)
        await asyncio.sleep(0.3)


@dp.callback_query(F.data == "kick_deleted_prepare")
async def cb_kick_prepare(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    try:
        _, deleted_count, _ = await build_stats_text(cb.message.chat.id)
    except Exception as e:
        await cb.answer(f"Scan error: {e}", show_alert=True)
        return

    await cb.message.reply(
        "🟥  <b>CONFIRM GHOST PURGE</b>\n"
        "<blockquote>━━━━━━━━━━━━━━━━━━━━━━━</blockquote>\n\n"
        f"☠️  Deleted accounts found » <code>{deleted_count}</code>\n\n"
        "<i>This will kick deleted accounts using ban + unban. Continue?</i>",
        reply_markup=purge_confirm_keyboard(),
    )
    await cb.answer()


@dp.callback_query(F.data == "kick_deleted_confirm")
async def cb_kick_confirm(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    await cb.answer("☠️ Purge sequence initiated…")
    chat_id = cb.message.chat.id

    if not await bot_can_ban(chat_id):
        await cb.message.reply("❌ <b>Missing bot permission:</b> <code>Ban Users</code>\n<i>Give the bot ban rights, then try again.</i>")
        return

    try:
        _, _, deleted_list = await full_scan(chat_id, force=True)
    except Exception as e:
        await cb.answer(f"Scan error: {e}", show_alert=True)
        return

    if not deleted_list:
        await cb.message.reply("✅  <b>Nothing to purge.</b>\n<i>No deleted accounts. Group is already clean.</i>  🗿", reply_markup=back_keyboard())
        return

    kicked = failed = 0
    for user in deleted_list:
        try:
            await bot.ban_chat_member(chat_id, user.id)
            await asyncio.sleep(KICK_DELAY_SECONDS)
            await bot.unban_chat_member(chat_id, user.id)
            kicked += 1
        except Exception as e:
            log.warning("Could not kick %s: %s", user.id, e)
            failed += 1

    scan_cache.pop(chat_id, None)
    verdict = "⚠️  <b>Zero accounts removed.</b>" if kicked == 0 else f"☠️  <b>{kicked} ghost{'s' if kicked != 1 else ''} wiped clean off this group.</b>"
    await cb.message.reply(
        "🗿  <b>P U R G E   C O M P L E T E</b>\n"
        "<blockquote>━━━━━━━━━━━━━━━━━━━━━━━━━━━</blockquote>\n\n"
        f"{verdict}\n\n"
        "<blockquote>"
        f"  👻  Kicked     ›   <code>{kicked}</code>\n"
        f"  💀  Failed     ›   <code>{failed}</code>"
        "</blockquote>\n\n"
        f"🔱  Executed by <a href=\"tg://user?id={OWNER_ID}\">Owner</a>\n\n"
        "<i>「 Ghosts don't belong here. Only the living remain. 」</i>  🗿",
        reply_markup=back_keyboard(),
    )

# ══════════════════════════════════════════════════════════════
#  CALLBACKS — ADMIN RIGHTS
# ══════════════════════════════════════════════════════════════
@dp.callback_query(F.data == "show_xdemote")
async def cb_show_xdemote(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    await cb.answer("🛡 Reading admins…")

    try:
        report_text, rows = await build_admin_report(cb.message.chat.id)
        await cb.message.reply(report_text)
        editable = [r for r in rows if r.editable][:ADMIN_CARDS_LIMIT]
        for r in editable:
            card = (
                f"{perm_emoji(r.score, r.total)}  <b>{esc(r.name)}</b>\n"
                "<blockquote>"
                f"  🪪  <code>{r.user_id}</code>   <i>{esc(r.username)}</i>\n"
                f"  🏷  Tag          :  <code>{esc(r.title)}</code>\n"
                f"  🔑  Permissions  :  {rights_bar(r.score, r.total)}"
                "</blockquote>"
            )
            await cb.message.reply(card, reply_markup=admin_card_keyboard(r.user_id))
            await asyncio.sleep(0.35)
    except Exception as e:
        await cb.answer(f"Error: {e}", show_alert=True)


@dp.callback_query(F.data.startswith("grant_admin_"))
async def cb_grant_admin(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    admin_id = int(cb.data.replace("grant_admin_", "", 1))
    await cb.answer("🟢 Granting full rights…")
    ok, result = await edit_single_admin(cb.message.chat.id, admin_id, "full")

    if ok:
        await cb.message.reply(
            "🟢  <b>FULL RIGHTS GRANTED</b>\n"
            "<blockquote>━━━━━━━━━━━━━━━━━━━━━━━━</blockquote>\n\n"
            f"🛡  Admin  <code>{admin_id}</code> — <b>{esc(result)}</b> now has full permissions.\n\n"
            "<i>Use Re-scan Admins to verify the new permission map.</i>",
            reply_markup=admin_done_keyboard(),
        )
    else:
        await cb.message.reply(
            f"❌  <b>Failed to grant rights.</b>\n<code>{esc(result)}</code>",
            reply_markup=admin_done_keyboard(),
        )


@dp.callback_query(F.data.startswith("strip_admin_"))
async def cb_strip_admin(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    admin_id = int(cb.data.replace("strip_admin_", "", 1))
    if admin_id == OWNER_ID:
        await cb.answer("🚫 Cannot strip owner rights.", show_alert=True)
        return

    await cb.answer("🔴 Stripping all rights…")
    ok, result = await edit_single_admin(cb.message.chat.id, admin_id, "strip")

    if ok:
        await cb.message.reply(
            "🔴  <b>ALL RIGHTS STRIPPED</b>\n"
            "<blockquote>━━━━━━━━━━━━━━━━━━━━━━━━</blockquote>\n\n"
            f"🛡  Admin  <code>{admin_id}</code> — <b>{esc(result)}</b> keeps only the admin tag/title.\n\n"
            "<i>Use Re-scan Admins to verify the new permission map.</i>",
            reply_markup=admin_done_keyboard(),
        )
    else:
        await cb.message.reply(
            f"❌  <b>Failed to strip rights.</b>\n<code>{esc(result)}</code>",
            reply_markup=admin_done_keyboard(),
        )

# ══════════════════════════════════════════════════════════════
#  ENTRY POINT — WEBHOOK MODE FOR VERCEL
# ══════════════════════════════════════════════════════════════
async def on_startup(app: web.Application):
    log.info("⚡ Connecting Telethon userbot…")
    await tele.start()
    log.info("✅ Telethon connected.")

    if WEBHOOK_URL:
        await bot.set_webhook(
            WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
        )
        log.info("✅ Telegram webhook set: %s", WEBHOOK_URL)
    else:
        log.warning("WEBHOOK_URL is empty. Set it in Vercel env vars.")


async def on_shutdown(app: web.Application):
    log.info("🛑 Shutting down…")
    await bot.session.close()
    await tele.disconnect()


async def health(request: web.Request):
    return web.json_response({
        "ok": True,
        "bot": "x-gc-manager",
        "mode": "webhook",
        "webhook_path": WEBHOOK_PATH,
    })


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", health)

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
    ).register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app


app = create_app()


if __name__ == "__main__":
    web.run_app(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
    )

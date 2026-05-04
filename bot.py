"""
⚡ 𝗫 𝗚𝗰 𝗠𝗮𝗻𝗴𝗲𝗿 𝗕𝗼𝘁
Kicks deleted Telegram accounts from a group.
Owner-only buttons. Hosted on Railway.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# ══════════════════════════════════════════════
#  CONFIG  — swap these before deploying
# ══════════════════════════════════════════════
BOT_TOKEN   = "YOUR_BOT_TOKEN_HERE"   # from @BotFather
OWNER_ID    = 6810553459
TARGET_CHAT = -1003419901372

# ══════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════
#  BOT + DISPATCHER
# ══════════════════════════════════════════════
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


# ══════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════
async def caller_is_admin(chat_id: int, user_id: int) -> bool:
    m = await bot.get_chat_member(chat_id, user_id)
    return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)


async def scan_deleted(chat_id: int) -> tuple[int, list]:
    """
    Scan group members.
    Bot API only freely exposes the admin list, so deleted-account detection
    works on admins + any member that carries is_deleted=True or an empty
    first_name ('Deleted Account').
    Returns (total_member_count, list_of_deleted_user_objects).
    """
    total  = await bot.get_chat_member_count(chat_id)
    admins = await bot.get_chat_administrators(chat_id)

    deleted = []
    for a in admins:
        u    = a.user
        name = (u.first_name or "").strip()
        if (
            getattr(u, "is_deleted", False)
            or name == ""
            or name.lower() == "deleted account"
        ):
            deleted.append(u)

    return total, deleted


def build_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="☠️  Kick Deleted Accs",
                    callback_data="kick_deleted",
                ),
                InlineKeyboardButton(
                    text="🔍  Info on Deleted",
                    callback_data="info_deleted",
                ),
            ]
        ]
    )


# ══════════════════════════════════════════════
#  /cutie  COMMAND
# ══════════════════════════════════════════════
@dp.message(Command("cutie"))
async def cutie_command(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Group guard
    if chat_id != TARGET_CHAT:
        return

    # Admin guard
    if not await caller_is_admin(chat_id, user_id):
        await message.reply(
            "⛔  <b>Permission Denied</b>\n"
            "<i>Only admins can wake me up.</i>  🗿"
        )
        return

    chat_info           = await bot.get_chat(chat_id)
    total, deleted_list = await scan_deleted(chat_id)

    deleted_count = len(deleted_list)
    alive_count   = total - deleted_count
    group_name    = chat_info.title or "This Group"
    group_handle  = f"@{chat_info.username}" if chat_info.username else "Private Group"

    # Find group owner name
    admins     = await bot.get_chat_administrators(chat_id)
    owner_name = "Unknown"
    for a in admins:
        if a.status == ChatMemberStatus.CREATOR:
            owner_name = a.user.full_name or a.user.username or "Unknown"
            break

    text = (
        "⚡  <b>𝗫 𝗚𝗰 𝗠𝗮𝗻𝗴𝗲𝗿 𝗕𝗼𝘁 — ONLINE</b>\n"
        "<blockquote>━━━━━━━━━━━━━━━━━━━━━━━</blockquote>\n\n"
        f"🏠  <b>Group</b>     »  <code>{group_name}</code>\n"
        f"🔗  <b>Handle</b>    »  {group_handle}\n"
        f"👑  <b>Owner</b>     »  <b>{owner_name}</b>\n\n"
        "<blockquote>📊  M E M B E R   B R E A K D O W N</blockquote>\n\n"
        f"👥  <b>Total Members</b>    ›  <code>{total}</code>\n"
        f"✅  <b>Alive Accounts</b>   ›  <code>{alive_count}</code>\n"
        f"☠️  <b>Deleted Accounts</b> ›  <code>{deleted_count}</code>\n\n"
        "<i>Pick your move, boss 👇</i>"
    )

    await message.reply(text, reply_markup=build_keyboard())


# ══════════════════════════════════════════════
#  CALLBACK — 🔍 INFO
# ══════════════════════════════════════════════
@dp.callback_query(F.data == "info_deleted")
async def cb_info(cb: CallbackQuery):
    if cb.from_user.id != OWNER_ID:
        await cb.answer("🚫  These buttons aren't for you.", show_alert=True)
        return

    await cb.answer("🔍  Scanning…")

    chat_id             = cb.message.chat.id
    _, deleted_list     = await scan_deleted(chat_id)

    if not deleted_list:
        await cb.message.reply(
            "✅  <b>No deleted accounts detected!</b>\n"
            "<i>Group is clean as a whistle 🧹</i>"
        )
        return

    lines = []
    for i, u in enumerate(deleted_list, 1):
        username = f"@{u.username}" if u.username else "<i>—</i>"
        name     = u.full_name or u.first_name or "Deleted Account"
        lines.append(
            f"  <b>{i}.</b>  ID: <code>{u.id}</code>   {username}\n"
            f"         └─ <i>{name}</i>"
        )

    body = "\n".join(lines)

    text = (
        "☠️  <b>DELETED ACCOUNT REPORT</b>\n"
        "<blockquote>━━━━━━━━━━━━━━━━━━━━━━━</blockquote>\n\n"
        f"<b>Ghosts Found :</b>  <code>{len(deleted_list)}</code>\n\n"
        f"{body}\n\n"
        "<blockquote><i>⚠️  Telegram Bot API only exposes admin members freely.\n"
        "For a full deep scan of all members, a userbot (Pyrogram / Telethon) is needed.</i></blockquote>"
    )

    await cb.message.reply(text)


# ══════════════════════════════════════════════
#  CALLBACK — ☠️ KICK
# ══════════════════════════════════════════════
@dp.callback_query(F.data == "kick_deleted")
async def cb_kick(cb: CallbackQuery):
    if cb.from_user.id != OWNER_ID:
        await cb.answer("🚫  These buttons aren't for you.", show_alert=True)
        return

    await cb.answer("☠️  Purge sequence initiated…", show_alert=False)

    chat_id             = cb.message.chat.id
    _, deleted_list     = await scan_deleted(chat_id)

    if not deleted_list:
        await cb.message.reply(
            "✅  <b>Nothing to purge.</b>\n"
            "<i>No deleted accounts found. Group is already clean.</i>  🗿"
        )
        return

    kicked = 0
    failed = 0

    for u in deleted_list:
        try:
            await bot.ban_chat_member(chat_id, u.id)
            await asyncio.sleep(0.05)
            await bot.unban_chat_member(chat_id, u.id)  # ban + unban = kick (no ban)
            kicked += 1
        except Exception as e:
            log.warning(f"Could not kick {u.id}: {e}")
            failed += 1

    mention = f'<a href="tg://user?id={OWNER_ID}">𝗖𝗶𝗽𝗵𝗲𝗿𝗫.𝗮𝗲</a>'

    if kicked == 0:
        verdict = "⚠️  <b>Zero accounts removed.</b>  Already gone or untouchable."
    elif kicked == 1:
        verdict = "☠️  <b>1 ghost has been erased from existence.</b>"
    else:
        verdict = f"☠️  <b>{kicked} ghosts wiped clean off the map.</b>"

    text = (
        "🗿  <b>P U R G E   C O M P L E T E</b>\n"
        "<blockquote>━━━━━━━━━━━━━━━━━━━━━━━━━━</blockquote>\n\n"
        f"{verdict}\n\n"
        "<blockquote>"
        f"  👻  Kicked     ›   <code>{kicked}</code>\n"
        f"  💀  Failed     ›   <code>{failed}</code>"
        "</blockquote>\n\n"
        f"🔱  Executed on the iron command of  {mention}\n\n"
        "<i>「 Ghosts don't belong here.  Only the living remain. 」</i>  🗿"
    )

    await cb.message.reply(text)


# ══════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════
async def main():
    log.info("⚡  X Gc Manger Bot — starting…")
    await dp.start_polling(
        bot,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    asyncio.run(main())

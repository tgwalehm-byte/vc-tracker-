# ============================================
# VC TRACKER BOT - MAIN
# ============================================

import asyncio
import logging

from datetime import datetime, timezone, timedelta

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    SESSION_STRING,
    LOG_CHANNEL,
    OWNER_ID,
    POLL_SECONDS,
)

from database import (
    add_tracked_group,
    remove_tracked_group,
    is_tracked,
    get_tracked_groups,
    get_stats,
    get_history,
)

from tracker import VCTracker


# ============================================
# LOGGING
# ============================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
)

log = logging.getLogger(__name__)


# ============================================
# BOT CLIENT
# ============================================

bot = Client(
    "vc_tracker_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)


# ============================================
# USER CLIENT
# ============================================

user = Client(
    "vc_tracker_user",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
)


# ============================================
# LOG CHANNEL
# ============================================

async def send_log(text):

    try:

        await bot.send_message(
            LOG_CHANNEL,
            text,
            disable_web_page_preview=True,
        )

    except Exception as e:

        log.error(
            "LOG CHANNEL ERROR: %s",
            e,
        )


# ============================================
# TRACKER
# ============================================

tracker = VCTracker(
    client=user,
    send_log=send_log,
    poll_seconds=POLL_SECONDS,
)


# ============================================
# RAW TELEGRAM UPDATE
# ============================================

@user.on_raw_update()
async def raw_update(
    client,
    update,
    users,
    chats,
):

    try:

        await tracker.update(
            update,
            users,
            chats,
        )

    except Exception:

        log.exception(
            "RAW UPDATE HANDLER ERROR"
        )


# ============================================
# ADMIN CHECK
# ============================================

async def is_admin(
    client,
    chat_id,
    user_id,
):

    # Bot owner
    if user_id == OWNER_ID:

        return True

    try:

        member = await client.get_chat_member(
            chat_id,
            user_id,
        )

        return member.status in (
            ChatMemberStatus.OWNER,
            ChatMemberStatus.ADMINISTRATOR,
        )

    except Exception as e:

        log.debug(
            "Admin check failed: %s",
            e,
        )

        return False


# ============================================
# /START
# ============================================

@bot.on_message(
    filters.command("start")
)
async def start_command(
    client,
    message,
):

    text = (
        "🎙️ <b>VC TRACKER BOT</b>\n\n"

        "🟢 VC JOIN tracking\n"
        "🔴 VC LEFT tracking\n"
        "⏱️ Exact session duration\n"
        "📊 Daily / Weekly / Monthly report\n"
        "📜 Session history\n"
        "🔄 Auto VC discovery\n\n"

        "━━━━━━━━━━━━━━━━━━\n\n"

        "<b>Commands</b>\n\n"

        "🎙️ /track\n"
        "Enable VC tracking in group\n\n"

        "🛑 /stoptrack\n"
        "Disable VC tracking\n\n"

        "📡 /status\n"
        "Check tracking status\n\n"

        "📋 /tracked\n"
        "Show tracked groups\n\n"

        "📊 /report\n"
        "Show your VC report\n\n"

        "📜 /history\n"
        "Show your last VC sessions"
    )

    await message.reply_text(
        text,
        disable_web_page_preview=True,
    )


# ============================================
# /TRACK
# ============================================

@bot.on_message(
    filters.command("track")
    & filters.group
)
async def track_command(
    client,
    message,
):

    if not message.from_user:

        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    # Admin / Owner only
    if not await is_admin(
        client,
        chat_id,
        user_id,
    ):

        await message.reply_text(
            "❌ <b>Permission Denied</b>\n\n"
            "Sirf group owner/admin "
            "ye command use kar sakta hai."
        )

        return

    title = (
        message.chat.title
        or "Unknown Group"
    )

    add_tracked_group(
        chat_id=chat_id,
        title=title,
        added_by=user_id,
    )

    await message.reply_text(
        "🟢 <b>VC TRACKING ENABLED</b>\n\n"

        f"🎙️ <b>Group:</b> {title}\n"
        f"🆔 <b>ID:</b> <code>{chat_id}</code>\n\n"

        "Ab is group ke VC ke:\n"
        "🟢 JOIN\n"
        "🔴 LEFT\n"
        "⏱️ Duration\n\n"

        "automatically track honge."
    )

    # Immediate VC discovery
    asyncio.create_task(
        tracker.discover_call(
            chat_id
        )
    )

    log.info(
        "TRACK ENABLED | chat=%s | by=%s",
        chat_id,
        user_id,
    )


# ============================================
# /STOPTRACK
# ============================================

@bot.on_message(
    filters.command("stoptrack")
    & filters.group
)
async def stoptrack_command(
    client,
    message,
):

    if not message.from_user:

        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_admin(
        client,
        chat_id,
        user_id,
    ):

        await message.reply_text(
            "❌ <b>Permission Denied</b>\n\n"
            "Sirf group owner/admin "
            "ye command use kar sakta hai."
        )

        return

    removed = remove_tracked_group(
        chat_id
    )

    if removed:

        await message.reply_text(
            "🔴 <b>VC TRACKING DISABLED</b>\n\n"
            "Is group ki VC tracking band kar di gayi hai."
        )

        log.info(
            "TRACK DISABLED | chat=%s | by=%s",
            chat_id,
            user_id,
        )

    else:

        await message.reply_text(
            "⚠️ Ye group abhi track nahi ho raha."
        )


# ============================================
# /STATUS
# ============================================

@bot.on_message(
    filters.command("status")
)
async def status_command(
    client,
    message,
):

    if message.chat.type.value not in (
        "group",
        "supergroup",
    ):

        await message.reply_text(
            "❌ Ye command group me use karo."
        )

        return

    chat_id = message.chat.id

    if is_tracked(chat_id):

        active_count = len(
            get_active_users_safe(
                chat_id
            )
        )

        await message.reply_text(
            "🟢 <b>VC TRACKING: ON</b>\n\n"
            f"🎙️ Group: {message.chat.title}\n"
            f"👥 Active tracked users: {active_count}"
        )

    else:

        await message.reply_text(
            "🔴 <b>VC TRACKING: OFF</b>\n\n"
            "Tracking start karne ke liye:\n"
            "<code>/track</code>"
        )


# ============================================
# ACTIVE USERS SAFE HELPER
# ============================================

def get_active_users_safe(
    chat_id
):

    try:

        from database import get_active_for_chat

        return get_active_for_chat(
            chat_id
        )

    except Exception:

        return []


# ============================================
# /TRACKED
# ============================================

@bot.on_message(
    filters.command("tracked")
)
async def tracked_command(
    client,
    message,
):

    groups = get_tracked_groups()

    if not groups:

        await message.reply_text(
            "❌ <b>No tracked groups.</b>"
        )

        return

    text = (
        "📋 <b>TRACKED GROUPS</b>\n\n"
    )

    for index, group in enumerate(
        groups,
        1,
    ):

        title = (
            group.get(
                "title",
                "Unknown",
            )
        )

        chat_id = group[
            "chat_id"
        ]

        text += (
            f"{index}️⃣ <b>{title}</b>\n"
            f"🆔 <code>{chat_id}</code>\n\n"
        )

    await message.reply_text(
        text
    )


# ============================================
# FORMAT DURATION
# ============================================

def format_duration(
    seconds
):

    seconds = max(
        0,
        int(seconds),
    )

    days, remainder = divmod(
        seconds,
        86400,
    )

    hours, remainder = divmod(
        remainder,
        3600,
    )

    minutes, seconds = divmod(
        remainder,
        60,
    )

    parts = []

    if days:
        parts.append(
            f"{days}d"
        )

    if hours:
        parts.append(
            f"{hours}h"
        )

    if minutes:
        parts.append(
            f"{minutes}m"
        )

    if seconds or not parts:
        parts.append(
            f"{seconds}s"
        )

    return " ".join(parts)


# ============================================
# /REPORT
# ============================================

@bot.on_message(
    filters.command("report")
)
async def report_command(
    client,
    message,
):

    if not message.from_user:

        return

    if message.chat.type.value not in (
        "group",
        "supergroup",
    ):

        await message.reply_text(
            "❌ <b>/report</b> group me use karo."
        )

        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    if not is_tracked(chat_id):

        await message.reply_text(
            "❌ Ye group track nahi ho raha."
        )

        return

    now = datetime.now(
        timezone.utc
    )

    # Today
    today_start = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    # Monday = start of week
    week_start = (
        today_start
        - timedelta(
            days=today_start.weekday()
        )
    )

    # Start of month
    month_start = today_start.replace(
        day=1
    )

    today = get_stats(
        user_id,
        chat_id,
        today_start,
    )

    week = get_stats(
        user_id,
        chat_id,
        week_start,
    )

    month = get_stats(
        user_id,
        chat_id,
        month_start,
    )

    user_obj = message.from_user

    name = (
        user_obj.first_name
        or "Unknown"
    )

    if user_obj.last_name:

        name += (
            f" {user_obj.last_name}"
        )

    username = (
        f"@{user_obj.username}"
        if user_obj.username
        else "No username"
    )

    # Active session
    active_session = None

    try:

        from database import get_active

        active_session = get_active(
            user_id,
            chat_id,
        )

    except Exception:

        active_session = None

    active_text = ""

    if active_session:

        live_seconds = int(
            (
                now
                - active_session["join_time"]
            ).total_seconds()
        )

        active_text = (
            "\n\n"
            "🟢 <b>CURRENT VC</b>\n"
            f"Joined: "
            f"{tracker.format_time(active_session['join_time'])}\n"
            f"⏱️ Live Time: "
            f"{format_duration(live_seconds)}"
        )

    text = (
        "📊 <b>VC USER REPORT</b>\n\n"

        f"👤 <b>Name:</b> {name}\n"
        f"🔗 <b>Username:</b> {username}\n"
        f"🆔 <b>ID:</b> "
        f"<code>{user_id}</code>\n\n"

        f"🎙️ <b>Group:</b> "
        f"{message.chat.title}\n\n"

        "━━━━━━━━━━━━━━━━━━\n\n"

        "📅 <b>TODAY</b>\n"
        f"🟢 Joined: {today['joined']}\n"
        f"🔴 Left: {today['left']}\n"
        f"⏱️ VC Time: "
        f"{format_duration(today['total'])}\n\n"

        "📆 <b>THIS WEEK</b>\n"
        f"🟢 Joined: {week['joined']}\n"
        f"🔴 Left: {week['left']}\n"
        f"⏱️ VC Time: "
        f"{format_duration(week['total'])}\n\n"

        "🗓️ <b>THIS MONTH</b>\n"
        f"🟢 Joined: {month['joined']}\n"
        f"🔴 Left: {month['left']}\n"
        f"⏱️ VC Time: "
        f"{format_duration(month['total'])}"

        f"{active_text}"
    )

    await message.reply_text(
        text
    )


# ============================================
# /HISTORY
# ============================================

@bot.on_message(
    filters.command("history")
)
async def history_command(
    client,
    message,
):

    if not message.from_user:

        return

    if message.chat.type.value not in (
        "group",
        "supergroup",
    ):

        await message.reply_text(
            "❌ <b>/history</b> group me use karo."
        )

        return

    rows = get_history(
        message.from_user.id,
        message.chat.id,
        10,
    )

    if not rows:

        await message.reply_text(
            "📜 <b>No VC history found.</b>"
        )

        return

    text = (
        "📜 <b>LAST 10 VC SESSIONS</b>\n\n"
    )

    for index, row in enumerate(
        rows,
        1,
    ):

        join_time = row[
            "join_time"
        ]

        leave_time = row[
            "leave_time"
        ]

        join_text = tracker.format_time(
            join_time
        )

        leave_text = tracker.format_time(
            leave_time
        )

        duration = format_duration(
            row.get(
                "duration_seconds",
                0,
            )
        )

        text += (
            f"{index}️⃣ "
            f"<b>{join_text}</b>\n"
            f"🔴 Left: {leave_text}\n"
            f"⏱️ Duration: {duration}\n\n"
        )

    await message.reply_text(
        text
    )


# ============================================
# ERROR HANDLER
# ============================================

@bot.on_message(
    filters.command("ping")
)
async def ping_command(
    client,
    message,
):

    await message.reply_text(
        "🏓 <b>PONG</b>\n\n"
        "🟢 Bot is working."
    )


# ============================================
# MAIN
# ============================================

async def main():

    log.info(
        "================================"
    )

    log.info(
        "STARTING VC TRACKER..."
    )

    log.info(
        "================================"
    )

    # ----------------------------------------
    # START USER SESSION
    # ----------------------------------------

    log.info(
        "Starting user session..."
    )

    await user.start()

    user_me = await user.get_me()

    log.info(
        "USER SESSION CONNECTED"
    )

    log.info(
        "User ID: %s",
        user_me.id,
    )

    log.info(
        "User Name: %s",
        user_me.first_name,
    )

    # ----------------------------------------
    # START BOT
    # ----------------------------------------

    log.info(
        "Starting bot..."
    )

    await bot.start()

    bot_me = await bot.get_me()

    log.info(
        "BOT CONNECTED"
    )

    log.info(
        "Bot Username: @%s",
        bot_me.username,
    )

    # ----------------------------------------
    # ONLINE MESSAGE
    # ----------------------------------------

    try:

        await send_log(
            "🟢 <b>VC TRACKER ONLINE</b>\n\n"

            f"🤖 <b>Bot:</b> "
            f"@{bot_me.username}\n"

            f"👤 <b>User Session:</b> "
            f"<code>{user_me.id}</code>\n\n"

            "🎙️ VC Tracking: READY\n"
            "📡 Raw Updates: READY\n"
            "🔄 Auto Discovery: READY\n"
            "🔁 Reconciliation: READY\n"
            "🗄️ MongoDB: READY"
        )

    except Exception:

        log.exception(
            "Online message failed"
        )

    # ----------------------------------------
    # DISCOVER TRACKED GROUPS
    # ----------------------------------------

    groups = get_tracked_groups()

    log.info(
        "Tracked groups found: %s",
        len(groups),
    )

    for group in groups:

        chat_id = group[
            "chat_id"
        ]

        asyncio.create_task(
            tracker.discover_call(
                chat_id
            )
        )

    # ----------------------------------------
    # START POLLER
    # ----------------------------------------

    poll_task = asyncio.create_task(
        tracker.poll()
    )

    log.info(
        "================================"
    )

    log.info(
        "VC TRACKER STARTED SUCCESSFULLY"
    )

    log.info(
        "================================"
    )

    # Keep process alive
    try:

        await asyncio.Event().wait()

    except asyncio.CancelledError:

        pass

    finally:

        log.info(
            "Stopping VC Tracker..."
        )

        tracker.running = False

        poll_task.cancel()

        try:

            await poll_task

        except asyncio.CancelledError:

            pass

        try:

            await user.stop()

        except Exception:

            pass

        try:

            await bot.stop()

        except Exception:

            pass

        log.info(
            "VC Tracker stopped."
        )


# ============================================
# RUN
# ============================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        log.info(
            "Keyboard interrupt."
        )

    except Exception:

        log.exception(
            "FATAL STARTUP ERROR"
        )
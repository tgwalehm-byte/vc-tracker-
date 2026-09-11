import asyncio
import logging

from datetime import (
    datetime,
    timezone,
    timedelta
)

from pyrogram import (
    Client,
    filters
)

from pyrogram.enums import (
    ChatMemberStatus
)

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    SESSION_STRING,
    LOG_CHANNEL,
    OWNER_ID,
    POLL_SECONDS
)

from database import (
    add_tracked_group,
    remove_tracked_group,
    is_tracked,
    get_tracked_groups,
    get_stats,
    get_history
)

from tracker import VCTracker


# ------------------------------------
# LOGGING
# ------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format=(
        "[%(asctime)s] "
        "[%(levelname)s] "
        "%(message)s"
    )
)

log = logging.getLogger(__name__)


# ------------------------------------
# CLIENTS
# ------------------------------------

bot = Client(
    "vc_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

user = Client(
    "vc_user",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)


# ------------------------------------
# LOG SENDER
# ------------------------------------

async def send_log(text):

    try:

        await bot.send_message(
            LOG_CHANNEL,
            text,
            disable_web_page_preview=True
        )

    except Exception:

        log.exception(
            "Failed to send channel log"
        )


# ------------------------------------
# TRACKER
# ------------------------------------

tracker = VCTracker(
    client=user,
    send_log=send_log,
    poll_seconds=POLL_SECONDS
)


# ------------------------------------
# RAW UPDATE
# ------------------------------------

@user.on_raw_update()
async def raw_update(
    client,
    update,
    users,
    chats
):

    await tracker.update(
        update,
        users
    )


# ------------------------------------
# ADMIN CHECK
# ------------------------------------

async def is_admin(
    client,
    chat_id,
    user_id
):

    if user_id == OWNER_ID:

        return True

    try:

        member = await client.get_chat_member(
            chat_id,
            user_id
        )

        return member.status in (
            ChatMemberStatus.OWNER,
            ChatMemberStatus.ADMINISTRATOR
        )

    except Exception:

        return False


# ------------------------------------
# START
# ------------------------------------

@bot.on_message(
    filters.command("start")
)
async def start(
    client,
    message
):

    await message.reply_text(
        "🎙️ <b>VC TRACKER</b>\n\n"

        "🟢 JOIN / LEFT tracking\n"
        "⏱️ Session duration\n"
        "📊 Daily / Weekly / Monthly report\n"
        "📜 Session history\n\n"

        "<b>Commands</b>\n\n"

        "/track - Track this group\n"
        "/stoptrack - Stop tracking\n"
        "/status - Tracking status\n"
        "/tracked - Tracked groups\n"
        "/report - VC report\n"
        "/history - Session history"
    )


# ------------------------------------
# TRACK
# ------------------------------------

@bot.on_message(
    filters.command("track")
    & filters.group
)
async def track(
    client,
    message
):

    if not message.from_user:

        return

    if not await is_admin(
        client,
        message.chat.id,
        message.from_user.id
    ):

        await message.reply_text(
            "❌ Only group admin/owner "
            "can use this command."
        )

        return

    add_tracked_group(
        chat_id=message.chat.id,
        title=message.chat.title or "Unknown",
        added_by=message.from_user.id
    )

    tracker.chat_calls.pop(
        message.chat.id,
        None
    )

    await message.reply_text(
        "🟢 <b>VC TRACKING ON</b>\n\n"

        f"🎙️ Group: "
        f"{message.chat.title}\n\n"

        "Ab is group ka VC "
        "JOIN / LEFT track hoga."
    )

    # Try immediate discovery
    asyncio.create_task(
        tracker.discover_call(
            message.chat.id
        )
    )


# ------------------------------------
# STOP TRACK
# ------------------------------------

@bot.on_message(
    filters.command("stoptrack")
    & filters.group
)
async def stoptrack(
    client,
    message
):

    if not message.from_user:

        return

    if not await is_admin(
        client,
        message.chat.id,
        message.from_user.id
    ):

        await message.reply_text(
            "❌ Only group admin/owner "
            "can use this command."
        )

        return

    removed = remove_tracked_group(
        message.chat.id
    )

    if removed:

        await message.reply_text(
            "🔴 <b>VC TRACKING OFF</b>"
        )

    else:

        await message.reply_text(
            "⚠️ Ye group track nahi ho raha."
        )


# ------------------------------------
# STATUS
# ------------------------------------

@bot.on_message(
    filters.command("status")
)
async def status(
    client,
    message
):

    if message.chat.type.value not in (
        "group",
        "supergroup"
    ):

        await message.reply_text(
            "❌ /status group me use karo."
        )

        return

    if is_tracked(
        message.chat.id
    ):

        await message.reply_text(
            "🟢 <b>VC TRACKING: ON</b>"
        )

    else:

        await message.reply_text(
            "🔴 <b>VC TRACKING: OFF</b>"
        )


# ------------------------------------
# TRACKED
# ------------------------------------

@bot.on_message(
    filters.command("tracked")
)
async def tracked_groups(
    client,
    message
):

    groups = get_tracked_groups()

    if not groups:

        await message.reply_text(
            "❌ No tracked groups."
        )

        return

    text = "🎙️ <b>TRACKED GROUPS</b>\n\n"

    for i, group in enumerate(
        groups,
        1
    ):

        text += (
            f"{i}️⃣ "
            f"<b>{group.get('title', 'Unknown')}</b>\n"
            f"🆔 <code>{group['chat_id']}</code>\n\n"
        )

    await message.reply_text(
        text
    )


# ------------------------------------
# REPORT
# ------------------------------------

@bot.on_message(
    filters.command("report")
)
async def report(
    client,
    message
):

    if not message.from_user:

        return

    if message.chat.type.value not in (
        "group",
        "supergroup"
    ):

        await message.reply_text(
            "❌ /report tracked group me use karo."
        )

        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    if not is_tracked(
        chat_id
    ):

        await message.reply_text(
            "❌ Ye group track nahi ho raha."
        )

        return

    now = datetime.now(
        timezone.utc
    )

    today_start = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    week_start = (
        today_start
        - timedelta(
            days=today_start.weekday()
        )
    )

    month_start = today_start.replace(
        day=1
    )

    today = get_stats(
        user_id,
        chat_id,
        today_start
    )

    week = get_stats(
        user_id,
        chat_id,
        week_start
    )

    month = get_stats(
        user_id,
        chat_id,
        month_start
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

    def fd(seconds):

        seconds = int(seconds)

        d, r = divmod(
            seconds,
            86400
        )

        h, r = divmod(
            r,
            3600
        )

        m, s = divmod(
            r,
            60
        )

        parts = []

        if d:
            parts.append(
                f"{d}d"
            )

        if h:
            parts.append(
                f"{h}h"
            )

        if m:
            parts.append(
                f"{m}m"
            )

        if s or not parts:
            parts.append(
                f"{s}s"
            )

        return " ".join(parts)

    text = (
        "📊 <b>VC USER REPORT</b>\n\n"

        f"👤 <b>Name:</b> {name}\n"
        f"🔗 <b>Username:</b> {username}\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"

        f"🎙️ <b>Group:</b> "
        f"{message.chat.title}\n\n"

        "📅 <b>TODAY</b>\n"
        f"🟢 Joined: {today['joined']}\n"
        f"🔴 Left: {today['left']}\n"
        f"⏱️ VC Time: {fd(today['total'])}\n\n"

        "📆 <b>THIS WEEK</b>\n"
        f"🟢 Joined: {week['joined']}\n"
        f"🔴 Left: {week['left']}\n"
        f"⏱️ VC Time: {fd(week['total'])}\n\n"

        "🗓️ <b>THIS MONTH</b>\n"
        f"🟢 Joined: {month['joined']}\n"
        f"🔴 Left: {month['left']}\n"
        f"⏱️ VC Time: {fd(month['total'])}"
    )

    await message.reply_text(
        text
    )


# ------------------------------------
# HISTORY
# ------------------------------------

@bot.on_message(
    filters.command("history")
)
async def history(
    client,
    message
):

    if not message.from_user:

        return

    if message.chat.type.value not in (
        "group",
        "supergroup"
    ):

        await message.reply_text(
            "❌ /history group me use karo."
        )

        return

    rows = get_history(
        message.from_user.id,
        message.chat.id,
        10
    )

    if not rows:

        await message.reply_text(
            "📜 No VC history found."
        )

        return

    text = (
        "📜 <b>LAST 10 VC SESSIONS</b>\n\n"
    )

    for i, row in enumerate(
        rows,
        1
    ):

        join = row[
            "join_time"
        ].astimezone().strftime(
            "%d-%m-%Y %I:%M:%S %p"
        )

        leave = row[
            "leave_time"
        ].astimezone().strftime(
            "%d-%m-%Y %I:%M:%S %p"
        )

        duration = tracker.format_duration(
            row.get(
                "duration_seconds",
                0
            )
        )

        text += (
            f"{i}️⃣ "
            f"{join}\n"
            f"   → {leave}\n"
            f"   ⏱️ {duration}\n\n"
        )

    await message.reply_text(
        text
    )


# ------------------------------------
# MAIN
# ------------------------------------

async def main():

    log.info(
        "Starting VC Tracker..."
    )

    # USER SESSION FIRST
    await user.start()

    user_me = await user.get_me()

    log.info(
        "User session connected: %s | %s",
        user_me.id,
        user_me.first_name
    )

    # BOT
    await bot.start()

    bot_me = await bot.get_me()

    log.info(
        "Bot connected: @%s",
        bot_me.username
    )

    # ONLINE MESSAGE
    await send_log(
        "🟢 <b>VC TRACKER ONLINE</b>\n\n"

        f"🤖 Bot: "
        f"@{bot_me.username}\n"

        f"👤 User Session: "
        f"<code>{user_me.id}</code>\n\n"

        "🎙️ VC Tracking: READY\n"
        "📡 Raw Updates: READY\n"
        "🔄 Auto Discovery: READY\n"
        "🔁 Reconciliation: READY\n"
        "🗄️ MongoDB: READY"
    )

    log.info(
        "VC Tracker started successfully."
    )

    # POLLER
    poll_task = asyncio.create_task(
        tracker.poll()
    )

    try:

        await asyncio.Event().wait()

    finally:

        tracker.running = False

        poll_task.cancel()

        try:
            await poll_task
        except asyncio.CancelledError:
            pass

        await user.stop()
        await bot.stop()


if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        pass
import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    SESSION_STRING,
    OWNER_ID,
    LOG_CHANNEL,
)

from database import (
    add_tracked_group,
    remove_tracked_group,
    is_tracked,
    get_tracked_groups,
    get_user_report,
)

from tracker import VCTracker


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    )
)

log = logging.getLogger(__name__)


bot = Client(
    "vc_tracker_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

user = Client(
    "vc_tracker_user",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)

tracker = None


def format_duration(seconds):

    seconds = int(seconds)

    days, seconds = divmod(
        seconds,
        86400
    )

    hours, seconds = divmod(
        seconds,
        3600
    )

    minutes, seconds = divmod(
        seconds,
        60
    )

    result = []

    if days:
        result.append(
            f"{days}d"
        )

    if hours:
        result.append(
            f"{hours}h"
        )

    if minutes:
        result.append(
            f"{minutes}m"
        )

    if seconds or not result:
        result.append(
            f"{seconds}s"
        )

    return " ".join(result)


async def is_admin(client, chat_id, user_id):

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


@bot.on_message(
    filters.command("start")
)
async def start_command(
    client,
    message
):

    await message.reply_text(
        "🟢 VC TRACKER ONLINE\n\n"
        "🎙️ Voice Chat JOIN / LEFT Tracker\n\n"
        "Commands:\n"
        "/track - Track this group\n"
        "/stoptrack - Stop tracking\n"
        "/status - Tracking status\n"
        "/tracked - Tracked groups\n"
        "/report - Your VC report"
    )


@bot.on_message(
    filters.command("track")
    & filters.group
)
async def track_command(
    client,
    message
):

    user_id = message.from_user.id

    if not await is_admin(
        client,
        message.chat.id,
        user_id
    ) and user_id != OWNER_ID:

        await message.reply_text(
            "❌ Sirf group admin/owner "
            "ye command use kar sakta hai."
        )

        return

    add_tracked_group(
        chat_id=message.chat.id,
        title=message.chat.title or "Unknown",
        added_by=user_id
    )

    tracker.chat_titles[
        message.chat.id
    ] = message.chat.title or "Unknown"

    await message.reply_text(
        "✅ VC TRACKING ON\n\n"
        f"🎙️ Group: {message.chat.title}\n\n"
        "Ab is group ke VC JOIN / LEFT "
        "track kiye jayenge."
    )


@bot.on_message(
    filters.command("stoptrack")
    & filters.group
)
async def stoptrack_command(
    client,
    message
):

    user_id = message.from_user.id

    if not await is_admin(
        client,
        message.chat.id,
        user_id
    ) and user_id != OWNER_ID:

        await message.reply_text(
            "❌ Sirf group admin/owner "
            "ye command use kar sakta hai."
        )

        return

    removed = remove_tracked_group(
        message.chat.id
    )

    if removed:

        await message.reply_text(
            "🔴 VC TRACKING OFF"
        )

    else:

        await message.reply_text(
            "⚠️ Ye group track nahi ho raha tha."
        )


@bot.on_message(
    filters.command("status")
)
async def status_command(
    client,
    message
):

    if message.chat.type.value in (
        "group",
        "supergroup"
    ):

        tracked = is_tracked(
            message.chat.id
        )

        status = (
            "🟢 ON"
            if tracked
            else "🔴 OFF"
        )

        await message.reply_text(
            f"🎙️ VC Tracking: {status}"
        )

    else:

        await message.reply_text(
            "Use /status inside the group."
        )


@bot.on_message(
    filters.command("tracked")
)
async def tracked_command(
    client,
    message
):

    groups = get_tracked_groups()

    if not groups:

        await message.reply_text(
            "❌ Koi group track nahi ho raha."
        )

        return

    text = "🎙️ TRACKED GROUPS\n\n"

    for index, group in enumerate(
        groups,
        1
    ):

        text += (
            f"{index}. {group.get('title', 'Unknown')}\n"
            f"🆔 `{group['chat_id']}`\n\n"
        )

    await message.reply_text(
        text
    )


@bot.on_message(
    filters.command("report")
)
async def report_command(
    client,
    message
):

    if not message.from_user:

        return

    if not message.chat:

        return

    chat_id = message.chat.id

    if not is_tracked(chat_id):

        await message.reply_text(
            "❌ Ye group track nahi ho raha."
        )

        return

    user_id = message.from_user.id

    report = get_user_report(
        user_id,
        chat_id
    )

    user = message.from_user

    name = user.first_name or "Unknown"

    if user.last_name:
        name += f" {user.last_name}"

    username = (
        f"@{user.username}"
        if user.username
        else "No username"
    )

    today_joined, today_left, today_time = (
        report["today"]
    )

    week_joined, week_left, week_time = (
        report["week"]
    )

    month_joined, month_left, month_time = (
        report["month"]
    )

    text = (
        "📊 VC USER REPORT\n\n"

        f"👤 Name: {name}\n"
        f"🔗 Username: {username}\n"
        f"🆔 ID: {user_id}\n\n"

        f"🎙️ Group: {message.chat.title}\n\n"

        "📅 TODAY\n"
        f"🟢 Joined: {today_joined}\n"
        f"🔴 Left: {today_left}\n"
        f"⏱️ VC Time: "
        f"{format_duration(today_time)}\n\n"

        "📆 THIS WEEK\n"
        f"🟢 Joined: {week_joined}\n"
        f"🔴 Left: {week_left}\n"
        f"⏱️ VC Time: "
        f"{format_duration(week_time)}\n\n"

        "🗓️ THIS MONTH\n"
        f"🟢 Joined: {month_joined}\n"
        f"🔴 Left: {month_left}\n"
        f"⏱️ VC Time: "
        f"{format_duration(month_time)}"
    )

    await message.reply_text(
        text
    )


async def main():

    global tracker

    log.info(
        "Starting VC Tracker..."
    )

    await user.start()

    me = await user.get_me()

    log.info(
        "User session: %s | %s",
        me.id,
        me.first_name
    )

    await bot.start()

    tracker = VCTracker(
        bot=bot,
        user=user
    )

    await bot.send_message(
        LOG_CHANNEL,
        "🟢 VC TRACKER ONLINE\n\n"
        f"🤖 Bot: @{(await bot.get_me()).username}\n"
        f"👤 User Session: {me.id}\n\n"
        "🎙️ VC Tracking: READY\n"
        "📡 Raw Updates: READY\n"
        "🔄 Auto Discovery: READY\n"
        "🗄️ MongoDB: READY"
    )

    log.info(
        "VC Tracker started successfully."
    )

    await asyncio.Event().wait()


if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:

        pass
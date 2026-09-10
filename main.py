import asyncio
import logging

from pyrogram import (
    Client,
    idle,
    filters
)

from pyrogram.enums import ChatType
from pyrogram.raw import types

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    SESSION_STRING,
    LOG_CHANNEL,
    OWNER_ID
)

from database import (
    add_tracked_group,
    remove_tracked_group,
    is_tracked,
    get_tracked_groups
)

from tracker import VCTracker


# =====================================
# LOGGING
# =====================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "[%(asctime)s] "
        "[%(levelname)s] "
        "%(message)s"
    )
)

log = logging.getLogger(__name__)


# =====================================
# BOT
# =====================================

bot = Client(
    "vc_tracker_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


# =====================================
# USER ACCOUNT
# =====================================

user = Client(
    "vc_tracker_user",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)


# =====================================
# SEND LOG
# =====================================

async def send_log(text):

    try:

        await bot.send_message(
            chat_id=LOG_CHANNEL,
            text=text,
            disable_web_page_preview=True
        )

    except Exception as e:

        log.exception(
            "LOG CHANNEL ERROR: %s",
            e
        )


# =====================================
# TRACKER
# =====================================

tracker = VCTracker(
    user,
    send_log
)


# =====================================
# OWNER CHECK
# =====================================

def is_owner(message):

    if not message.from_user:
        return False

    return (
        message.from_user.id
        == OWNER_ID
    )


# =====================================
# RAW UPDATE
# =====================================

@user.on_raw_update()
async def raw_update(
    client,
    update,
    users,
    chats
):

    try:

        # =================================
        # GROUP CALL UPDATE
        # =================================

        if isinstance(
            update,
            types.UpdateGroupCall
        ):

            call = update.call


            raw_chat_id = getattr(
                update,
                "chat_id",
                None
            )


            if raw_chat_id is None:
                return


            # Telegram channel/supergroup ID
            chat_id = (
                -1000000000000
                - int(raw_chat_id)
            )


            # Only selected groups
            if not is_tracked(
                chat_id
            ):

                return


            await tracker.register_call(
                chat_id,
                call
            )


            # VC ended
            if isinstance(
                call,
                types.GroupCallDiscarded
            ):

                tracker.end_call(
                    call
                )


            return


        # =================================
        # PARTICIPANT UPDATE
        # =================================

        if isinstance(
            update,
            types.UpdateGroupCallParticipants
        ):

            call = update.call


            call_id = getattr(
                call,
                "id",
                None
            )


            if not call_id:
                return


            if call_id not in tracker.calls:
                return


            for participant in (
                update.participants
            ):

                await tracker.participant(
                    call,
                    participant,
                    users
                )


    except Exception as e:

        log.exception(
            "VC RAW UPDATE ERROR: %s",
            e
        )


# =====================================
# /START
# =====================================

@bot.on_message(
    filters.command("start")
)
async def start_command(
    client,
    message
):

    user_id = (
        message.from_user.id
        if message.from_user
        else 0
    )


    log.info(
        "START COMMAND | User=%s | Owner=%s",
        user_id,
        OWNER_ID
    )


    # =================================
    # NOT OWNER
    # =================================

    if user_id != OWNER_ID:

        await message.reply_text(
            "❌ <b>Access Denied</b>\n\n"
            "🔒 This bot is private."
        )

        return


    # =================================
    # OWNER
    # =================================

    await message.reply_text(
        "👑 <b>VC TRACKER OWNER PANEL</b>\n\n"

        "🎙️ <b>Voice Chat Tracker</b>\n"
        "⚡ System is online.\n\n"

        "📌 <b>Commands</b>\n\n"

        "➕ <code>/track</code>\n"
        "Track current group\n\n"

        "➖ <code>/stoptrack</code>\n"
        "Stop current group\n\n"

        "📊 <code>/status</code>\n"
        "Check current group\n\n"

        "📋 <code>/tracked</code>\n"
        "Show all tracked groups\n\n"

        "💡 <b>Use:</b>\n"
        "Group ke andar <code>/track</code> bhejo."
    )


# =====================================
# /TRACK
# =====================================

@bot.on_message(
    filters.command("track")
)
async def track_command(
    client,
    message
):

    if not is_owner(message):
        return


    # Only group
    if message.chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP
    ):

        await message.reply_text(
            "❌ <b>Group ke andar /track use karo.</b>"
        )

        return


    chat_id = message.chat.id

    title = (
        message.chat.title
        or "Unknown Group"
    )


    # Already tracking
    if is_tracked(
        chat_id
    ):

        await message.reply_text(
            "⚠️ <b>Already Tracking</b>\n\n"

            f"🎙️ <b>Group:</b> "
            f"{title}\n"

            f"🆔 <code>{chat_id}</code>"
        )

        return


    # Save group
    add_tracked_group(
        chat_id=chat_id,
        title=title,
        added_by=OWNER_ID
    )


    await message.reply_text(
        "✅ <b>VC TRACKING ENABLED</b>\n\n"

        f"🎙️ <b>Group:</b> "
        f"{title}\n"

        f"🆔 <code>{chat_id}</code>\n\n"

        "🟢 JOIN tracking: ON\n"
        "🔴 LEAVE tracking: ON\n"
        "💾 MongoDB: ON\n"
        "📢 Channel logs: ON\n\n"

        "⚡ Ab is group ka VC track hoga."
    )


    log.info(
        "TRACK ENABLED | Group=%s | ID=%s",
        title,
        chat_id
    )


# =====================================
# /STOPTRACK
# =====================================

@bot.on_message(
    filters.command("stoptrack")
)
async def stoptrack_command(
    client,
    message
):

    if not is_owner(message):
        return


    if message.chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP
    ):

        await message.reply_text(
            "❌ <b>Group ke andar /stoptrack use karo.</b>"
        )

        return


    chat_id = message.chat.id

    title = (
        message.chat.title
        or "Unknown Group"
    )


    removed = remove_tracked_group(
        chat_id
    )


    if not removed:

        await message.reply_text(
            "⚠️ <b>This group is not being tracked.</b>"
        )

        return


    await message.reply_text(
        "🛑 <b>VC TRACKING DISABLED</b>\n\n"

        f"🎙️ <b>Group:</b> "
        f"{title}"
    )


    log.info(
        "TRACK DISABLED | Group=%s | ID=%s",
        title,
        chat_id
    )


# =====================================
# /STATUS
# =====================================

@bot.on_message(
    filters.command("status")
)
async def status_command(
    client,
    message
):

    if not is_owner(message):
        return


    if message.chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP
    ):

        await message.reply_text(
            "❌ <b>Group ke andar /status use karo.</b>"
        )

        return


    chat_id = message.chat.id

    title = (
        message.chat.title
        or "Unknown Group"
    )


    if is_tracked(
        chat_id
    ):

        await message.reply_text(
            "🟢 <b>TRACKING ACTIVE</b>\n\n"

            f"🎙️ <b>Group:</b> "
            f"{title}\n"

            f"🆔 <code>{chat_id}</code>"
        )

    else:

        await message.reply_text(
            "🔴 <b>TRACKING DISABLED</b>\n\n"

            f"🎙️ <b>Group:</b> "
            f"{title}"
        )


# =====================================
# /TRACKED
# =====================================

@bot.on_message(
    filters.command("tracked")
)
async def tracked_command(
    client,
    message
):

    if not is_owner(message):
        return


    groups = get_tracked_groups()


    if not groups:

        await message.reply_text(
            "📋 <b>No groups are being tracked.</b>"
        )

        return


    text = (
        "📋 <b>TRACKED GROUPS</b>\n\n"
    )


    for index, group in enumerate(
        groups,
        1
    ):

        text += (
            f"{index}. 🎙️ "
            f"<b>{group.get('title', 'Unknown')}</b>\n"
            f"🆔 <code>{group['chat_id']}</code>\n\n"
        )


    await message.reply_text(
        text
    )


# =====================================
# MAIN
# =====================================

async def main():

    log.info(
        "===================================="
    )

    log.info(
        "Starting VC Tracker..."
    )

    log.info(
        "Owner ID: %s",
        OWNER_ID
    )

    log.info(
        "===================================="
    )


    # =================================
    # START BOT
    # =================================

    await bot.start()

    log.info(
        "Bot started successfully."
    )


    # =================================
    # START USER
    # =================================

    await user.start()

    log.info(
        "User session started successfully."
    )


    # =================================
    # USER INFO
    # =================================

    try:

        me = await user.get_me()

        log.info(
            "Tracking account: %s | ID: %s",
            me.first_name,
            me.id
        )

    except Exception as e:

        log.warning(
            "Could not get user information: %s",
            e
        )


    log.info(
        "VC Tracker is READY."
    )


    # =================================
    # KEEP RUNNING
    # =================================

    await idle()


    # =================================
    # STOP
    # =================================

    log.info(
        "Stopping VC Tracker..."
    )


    await user.stop()

    await bot.stop()


# =====================================
# RUN
# =====================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        log.info(
            "Bot stopped manually."
        )
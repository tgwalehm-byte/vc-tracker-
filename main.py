import asyncio
import logging

from pyrogram import Client, idle, filters
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


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s"
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
# LOG CHANNEL
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


tracker = VCTracker(
    user,
    send_log
)


# =====================================
# OWNER CHECK
# =====================================

def is_owner(message):
    return (
        message.from_user
        and message.from_user.id == OWNER_ID
    )


# =====================================
# RAW VC UPDATES
# =====================================

@user.on_raw_update()
async def raw_update(
    client,
    update,
    users,
    chats
):
    try:

        # -----------------------------
        # GROUP CALL CREATED / UPDATED
        # -----------------------------

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

            chat_id = (
                -1000000000000
                - int(raw_chat_id)
            )

            # Only track selected groups
            if not is_tracked(chat_id):
                return

            await tracker.register_call(
                chat_id,
                call
            )

            if isinstance(
                call,
                types.GroupCallDiscarded
            ):
                tracker.end_call(call)

            return


        # -----------------------------
        # VC PARTICIPANT UPDATE
        # -----------------------------

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

            for participant in update.participants:

                await tracker.participant(
                    call,
                    participant,
                    users
                )

    except Exception as e:

        log.exception(
            "VC UPDATE ERROR: %s",
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

    if not is_owner(message):

        await message.reply_text(
            "❌ <b>Access Denied</b>\n\n"
            "This bot is private."
        )

        return


    await message.reply_text(
        "👑 <b>VC TRACKER OWNER PANEL</b>\n\n"

        "🎙️ <b>Voice Chat Tracker</b>\n\n"

        "📌 <b>Commands:</b>\n\n"

        "➕ <code>/track</code> "
        "— Track this group\n"

        "➖ <code>/stoptrack</code> "
        "— Stop tracking this group\n"

        "📊 <code>/status</code> "
        "— Current group status\n"

        "📋 <code>/tracked</code> "
        "— Tracked groups list\n\n"

        "⚡ <b>How to use:</b>\n"
        "Group me jao aur <code>/track</code> bhejo."
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


    # Must be used inside a group
    if message.chat.type not in (
        "group",
        "supergroup"
    ):

        await message.reply_text(
            "❌ <b>Group ke andar /track use karo.</b>"
        )

        return


    chat_id = message.chat.id
    title = message.chat.title or "Unknown Group"


    if is_tracked(chat_id):

        await message.reply_text(
            "⚠️ <b>Already Tracking</b>\n\n"
            f"🎙️ <b>Group:</b> {title}\n"
            f"🆔 <code>{chat_id}</code>"
        )

        return


    add_tracked_group(
        chat_id=chat_id,
        title=title,
        added_by=OWNER_ID
    )


    await message.reply_text(
        "✅ <b>VC TRACKING ENABLED</b>\n\n"
        f"🎙️ <b>Group:</b> {title}\n"
        f"🆔 <code>{chat_id}</code>\n\n"
        "🟢 JOIN tracking: ON\n"
        "🔴 LEAVE tracking: ON\n"
        "💾 MongoDB: ON\n"
        "📢 Logs: ON"
    )

    log.info(
        "Tracking enabled: %s (%s)",
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
        "group",
        "supergroup"
    ):

        await message.reply_text(
            "❌ Group ke andar /stoptrack use karo."
        )

        return


    chat_id = message.chat.id
    title = message.chat.title or "Unknown Group"


    removed = remove_tracked_group(
        chat_id
    )


    if not removed:

        await message.reply_text(
            "⚠️ Ye group tracking me nahi hai."
        )

        return


    await message.reply_text(
        "🛑 <b>VC TRACKING DISABLED</b>\n\n"
        f"🎙️ <b>Group:</b> {title}"
    )

    log.info(
        "Tracking disabled: %s (%s)",
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
        "group",
        "supergroup"
    ):

        await message.reply_text(
            "❌ Group ke andar /status use karo."
        )

        return


    chat_id = message.chat.id
    title = message.chat.title or "Unknown Group"


    if is_tracked(chat_id):

        await message.reply_text(
            "🟢 <b>TRACKING ACTIVE</b>\n\n"
            f"🎙️ <b>Group:</b> {title}\n"
            f"🆔 <code>{chat_id}</code>"
        )

    else:

        await message.reply_text(
            "🔴 <b>TRACKING DISABLED</b>\n\n"
            f"🎙️ <b>Group:</b> {title}"
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


    for number, group in enumerate(
        groups,
        1
    ):

        text += (
            f"{number}. 🎙️ "
            f"<b>{group.get('title', 'Unknown')}</b>\n"
            f"   🆔 <code>{group['chat_id']}</code>\n\n"
        )


    await message.reply_text(text)


# =====================================
# START BOT
# =====================================

async def main():

    log.info(
        "===================================="
    )

    log.info(
        "Starting VC Tracker..."
    )

    log.info(
        "===================================="
    )


    await bot.start()

    log.info(
        "Bot started successfully."
    )


    await user.start()

    log.info(
        "User session started successfully."
    )


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


    await idle()


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

        asyncio.run(main())

    except KeyboardInterrupt:

        log.info(
            "Bot stopped manually."
        )
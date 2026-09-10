import asyncio
import logging

from pyrogram import Client, idle, filters
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


# ==========================================
# LOGGING
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s"
)

log = logging.getLogger(__name__)


# ==========================================
# BOT CLIENT
# ==========================================

bot = Client(
    "vc_tracker_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


# ==========================================
# USER CLIENT
# ==========================================

user = Client(
    "vc_tracker_user",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)


# ==========================================
# SEND LOG TO CHANNEL
# ==========================================

async def send_log(text):

    try:
        await bot.send_message(
            LOG_CHANNEL,
            text,
            disable_web_page_preview=True
        )

    except Exception as e:

        log.exception(
            "LOG CHANNEL ERROR: %s",
            e
        )


# ==========================================
# TRACKER
# ==========================================

tracker = VCTracker(
    user,
    send_log
)


# ==========================================
# OWNER CHECK
# ==========================================

def is_owner(message):

    if not message.from_user:
        return False

    return message.from_user.id == OWNER_ID


# ==========================================
# DEBUG - EVERY MESSAGE
# ==========================================

@bot.on_message(
    filters.incoming
)
async def debug_messages(
    client,
    message
):

    try:

        user_id = (
            message.from_user.id
            if message.from_user
            else None
        )

        text = (
            message.text
            or message.caption
            or ""
        )

        log.info(
            "BOT MESSAGE RECEIVED | "
            "User=%s | Chat=%s | Text=%s",
            user_id,
            message.chat.id if message.chat else None,
            text
        )

    except Exception as e:

        log.exception(
            "DEBUG HANDLER ERROR: %s",
            e
        )


# ==========================================
# START
# ==========================================

@bot.on_message(
    filters.command("start")
)
async def start_command(
    client,
    message
):

    try:

        user_id = (
            message.from_user.id
            if message.from_user
            else 0
        )

        log.info(
            "START COMMAND RECEIVED | "
            "User=%s | Owner=%s",
            user_id,
            OWNER_ID
        )


        # ----------------------------------
        # OWNER
        # ----------------------------------

        if user_id == OWNER_ID:

            await message.reply_text(
                "👑 <b>VC TRACKER</b>\n\n"

                "✅ <b>Bot is working!</b>\n\n"

                "🎙️ Voice Chat Tracker\n"
                "💾 MongoDB: Connected\n"
                "📢 Log System: ON\n\n"

                "📌 <b>Commands</b>\n\n"

                "➕ <code>/track</code>\n"
                "Track this group\n\n"

                "➖ <code>/stoptrack</code>\n"
                "Stop tracking this group\n\n"

                "📊 <code>/status</code>\n"
                "Check group status\n\n"

                "📋 <code>/tracked</code>\n"
                "Show tracked groups"
            )

        else:

            await message.reply_text(
                "❌ <b>Access Denied</b>\n\n"
                "🔒 This bot is private."
            )


    except Exception as e:

        log.exception(
            "START HANDLER ERROR: %s",
            e
        )


# ==========================================
# TRACK
# ==========================================

@bot.on_message(
    filters.command("track")
)
async def track_command(
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
            "❌ <b>Group ke andar /track bhejo.</b>"
        )

        return


    chat_id = message.chat.id

    title = (
        message.chat.title
        or "Unknown Group"
    )


    if is_tracked(chat_id):

        await message.reply_text(
            "⚠️ <b>Already Tracking</b>\n\n"
            f"🎙️ <b>Group:</b> {title}"
        )

        return


    add_tracked_group(
        chat_id,
        title,
        OWNER_ID
    )


    await message.reply_text(
        "✅ <b>VC TRACKING ENABLED</b>\n\n"

        f"🎙️ <b>Group:</b> {title}\n"
        f"🆔 <code>{chat_id}</code>\n\n"

        "🟢 JOIN: ON\n"
        "🔴 LEAVE: ON\n"
        "💾 MongoDB: ON\n"
        "📢 Logs: ON"
    )


    log.info(
        "TRACK ENABLED | %s | %s",
        title,
        chat_id
    )


# ==========================================
# STOP TRACK
# ==========================================

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
            "❌ Group ke andar /stoptrack bhejo."
        )

        return


    chat_id = message.chat.id

    title = (
        message.chat.title
        or "Unknown Group"
    )


    if remove_tracked_group(chat_id):

        await message.reply_text(
            "🛑 <b>TRACKING STOPPED</b>\n\n"
            f"🎙️ <b>Group:</b> {title}"
        )

        log.info(
            "TRACK DISABLED | %s | %s",
            title,
            chat_id
        )

    else:

        await message.reply_text(
            "⚠️ Ye group tracking me nahi hai."
        )


# ==========================================
# STATUS
# ==========================================

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
            "❌ Group ke andar /status bhejo."
        )

        return


    chat_id = message.chat.id

    title = (
        message.chat.title
        or "Unknown Group"
    )


    if is_tracked(chat_id):

        await message.reply_text(
            "🟢 <b>TRACKING ACTIVE</b>\n\n"
            f"🎙️ <b>Group:</b> {title}\n"
            f"🆔 <code>{chat_id}</code>"
        )

    else:

        await message.reply_text(
            "🔴 <b>TRACKING OFF</b>\n\n"
            f"🎙️ <b>Group:</b> {title}"
        )


# ==========================================
# TRACKED GROUPS
# ==========================================

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
            "📋 <b>No tracked groups.</b>"
        )

        return


    text = "📋 <b>TRACKED GROUPS</b>\n\n"


    for i, group in enumerate(
        groups,
        1
    ):

        text += (
            f"{i}. 🎙️ "
            f"<b>{group.get('title', 'Unknown')}</b>\n"
            f"🆔 <code>{group['chat_id']}</code>\n\n"
        )


    await message.reply_text(
        text
    )


# ==========================================
# RAW VC UPDATE
# ==========================================

@user.on_raw_update()
async def raw_update(
    client,
    update,
    users,
    chats
):

    try:

        # ----------------------------------
        # GROUP CALL
        # ----------------------------------

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

                tracker.end_call(
                    call
                )

            return


        # ----------------------------------
        # PARTICIPANTS
        # ----------------------------------

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


# ==========================================
# MAIN
# ==========================================

async def main():

    log.info(
        "===================================="
    )

    log.info(
        "STARTING VC TRACKER"
    )

    log.info(
        "OWNER ID: %s",
        OWNER_ID
    )

    log.info(
        "===================================="
    )


    # ----------------------------------
    # START BOT
    # ----------------------------------

    await bot.start()

    log.info(
        "BOT STARTED SUCCESSFULLY"
    )


    # ----------------------------------
    # BOT INFO
    # ----------------------------------

    try:

        bot_me = await bot.get_me()

        log.info(
            "BOT ACCOUNT: @%s | ID: %s",
            bot_me.username,
            bot_me.id
        )

    except Exception as e:

        log.exception(
            "BOT INFO ERROR: %s",
            e
        )


    # ----------------------------------
    # START USER
    # ----------------------------------

    await user.start()

    log.info(
        "USER SESSION STARTED SUCCESSFULLY"
    )


    try:

        user_me = await user.get_me()

        log.info(
            "TRACKING ACCOUNT: %s | ID: %s",
            user_me.first_name,
            user_me.id
        )

    except Exception as e:

        log.exception(
            "USER INFO ERROR: %s",
            e
        )


    log.info(
        "===================================="
    )

    log.info(
        "VC TRACKER IS READY"
    )

    log.info(
        "WAITING FOR TELEGRAM MESSAGES..."
    )

    log.info(
        "===================================="
    )


    await idle()


    log.info(
        "STOPPING..."
    )


    await user.stop()

    await bot.stop()


# ==========================================
# RUN
# ==========================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        log.info(
            "BOT STOPPED"
        )
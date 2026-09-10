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


# ==================================================
# LOGGING
# ==================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s"
)

log = logging.getLogger(__name__)


# ==================================================
# BOT
# ==================================================

bot = Client(
    "vc_tracker_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


# ==================================================
# USER
# ==================================================

user = Client(
    "vc_tracker_user",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)


# ==================================================
# LOG CHANNEL
# ==================================================

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


# ==================================================
# TRACKER
# ==================================================

tracker = VCTracker(
    user,
    send_log
)


# ==================================================
# OWNER
# ==================================================

def owner(message):

    return bool(
        message.from_user
        and message.from_user.id == OWNER_ID
    )


# ==================================================
# BOT COMMAND HANDLER
# ==================================================

@bot.on_message(
    filters.command(
        [
            "start",
            "track",
            "stoptrack",
            "status",
            "tracked"
        ]
    )
)
async def commands(
    client,
    message
):

    try:

        user_id = (
            message.from_user.id
            if message.from_user
            else 0
        )


        command = (
            message.command[0].lower()
            if message.command
            else ""
        )


        log.info(
            "COMMAND RECEIVED | "
            "command=%s | user=%s | chat=%s",
            command,
            user_id,
            message.chat.id
        )


        # ==========================================
        # START
        # ==========================================

        if command == "start":

            if not owner(message):

                await message.reply_text(
                    "❌ <b>Access Denied</b>\n\n"
                    "🔒 This bot is private."
                )

                return


            await message.reply_text(
                "👑 <b>VC TRACKER OWNER PANEL</b>\n\n"

                "🟢 <b>Bot is working!</b>\n\n"

                "🎙️ Voice Chat Tracker\n"
                "💾 MongoDB: ON\n"
                "📢 Log Channel: ON\n\n"

                "━━━━━━━━━━━━━━━━━━\n\n"

                "➕ <code>/track</code>\n"
                "Track current group\n\n"

                "➖ <code>/stoptrack</code>\n"
                "Stop current group\n\n"

                "📊 <code>/status</code>\n"
                "Current group status\n\n"

                "📋 <code>/tracked</code>\n"
                "All tracked groups"
            )

            return


        # ==========================================
        # OWNER ONLY
        # ==========================================

        if not owner(message):

            await message.reply_text(
                "❌ <b>Access Denied</b>"
            )

            return


        # ==========================================
        # TRACK
        # ==========================================

        if command == "track":

            if message.chat.type not in (
                ChatType.GROUP,
                ChatType.SUPERGROUP
            ):

                await message.reply_text(
                    "❌ <b>/track group ke andar use karo.</b>"
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
                    f"🎙️ {title}\n"
                    f"🆔 <code>{chat_id}</code>"
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

            return


        # ==========================================
        # STOP TRACK
        # ==========================================

        if command == "stoptrack":

            if message.chat.type not in (
                ChatType.GROUP,
                ChatType.SUPERGROUP
            ):

                await message.reply_text(
                    "❌ Group ke andar /stoptrack use karo."
                )

                return


            chat_id = message.chat.id

            title = (
                message.chat.title
                or "Unknown Group"
            )


            if remove_tracked_group(
                chat_id
            ):

                await message.reply_text(
                    "🛑 <b>TRACKING STOPPED</b>\n\n"
                    f"🎙️ {title}"
                )

            else:

                await message.reply_text(
                    "⚠️ Ye group tracking me nahi hai."
                )

            return


        # ==========================================
        # STATUS
        # ==========================================

        if command == "status":

            if message.chat.type not in (
                ChatType.GROUP,
                ChatType.SUPERGROUP
            ):

                await message.reply_text(
                    "❌ Group ke andar /status use karo."
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
                    f"🎙️ <b>{title}</b>\n"
                    f"🆔 <code>{chat_id}</code>"
                )

            else:

                await message.reply_text(
                    "🔴 <b>TRACKING OFF</b>\n\n"
                    f"🎙️ <b>{title}</b>"
                )

            return


        # ==========================================
        # TRACKED
        # ==========================================

        if command == "tracked":

            groups = get_tracked_groups()


            if not groups:

                await message.reply_text(
                    "📋 <b>No tracked groups.</b>"
                )

                return


            text = (
                "📋 <b>TRACKED GROUPS</b>\n\n"
            )


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

            return


    except Exception as e:

        log.exception(
            "COMMAND ERROR: %s",
            e
        )


# ==================================================
# RAW VC UPDATES
# ==================================================

@user.on_raw_update()
async def raw_update(
    client,
    update,
    users,
    chats
):

    try:

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
            "RAW VC ERROR: %s",
            e
        )


# ==================================================
# MAIN
# ==================================================

async def main():

    log.info(
        "======================================"
    )

    log.info(
        "STARTING VC TRACKER"
    )

    log.info(
        "OWNER_ID = %s",
        OWNER_ID
    )

    log.info(
        "======================================"
    )


    # ==========================================
    # BOT
    # ==========================================

    await bot.start()

    log.info(
        "BOT STARTED"
    )


    bot_me = await bot.get_me()

    log.info(
        "BOT = @%s | ID=%s",
        bot_me.username,
        bot_me.id
    )


    # ==========================================
    # USER
    # ==========================================

    await user.start()

    log.info(
        "USER SESSION STARTED"
    )


    user_me = await user.get_me()

    log.info(
        "TRACKING USER = %s | ID=%s",
        user_me.first_name,
        user_me.id
    )


    # ==========================================
    # STARTUP MESSAGE
    # ==========================================

    try:

        await bot.send_message(
            OWNER_ID,

            "🟢 <b>VC TRACKER ONLINE</b>\n\n"
            "Bot successfully started.\n\n"
            "👉 Send /start"
        )


        log.info(
            "OWNER STARTUP MESSAGE SENT"
        )

    except Exception as e:

        log.exception(
            "STARTUP MESSAGE ERROR: %s",
            e
        )


    # ==========================================
    # READY
    # ==========================================

    log.info(
        "======================================"
    )

    log.info(
        "VC TRACKER READY"
    )

    log.info(
        "WAITING FOR COMMANDS..."
    )

    log.info(
        "======================================"
    )


    await idle()


    await user.stop()

    await bot.stop()


# ==================================================
# RUN
# ==================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )
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
# USER SESSION
# ==================================================

user = Client(
    "vc_tracker_user",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)


# ==================================================
# SEND LOG
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
# OWNER CHECK
# ==================================================

def is_owner(message):

    if not message.from_user:
        return False

    return (
        message.from_user.id == OWNER_ID
    )


# ==================================================
# COMMAND NAME
# ==================================================

def get_command(message):

    text = (
        message.text
        or message.caption
        or ""
    )

    text = text.strip()

    if not text:
        return ""

    first = text.split()[0]

    if not first.startswith("/"):
        return ""

    command = first[1:]

    # /start@BotUsername
    if "@" in command:
        command = command.split("@")[0]

    return command.lower()


# ==================================================
# ⭐ SINGLE BOT MESSAGE HANDLER
# ==================================================

@bot.on_message(
    filters.incoming
)
async def bot_message_handler(
    client,
    message
):

    try:

        # ------------------------------------------
        # BASIC INFORMATION
        # ------------------------------------------

        user_id = (
            message.from_user.id
            if message.from_user
            else None
        )

        chat_id = (
            message.chat.id
            if message.chat
            else None
        )

        command = get_command(
            message
        )


        log.info(
            "BOT MESSAGE | user=%s | chat=%s | command=%s",
            user_id,
            chat_id,
            command
        )


        # ------------------------------------------
        # NO COMMAND
        # ------------------------------------------

        if not command:
            return


        # ------------------------------------------
        # OWNER
        # ------------------------------------------

        owner = (
            user_id == OWNER_ID
        )


        # ==================================================
        # /START
        # ==================================================

        if command == "start":

            if not owner:

                await message.reply_text(
                    "❌ <b>Access Denied</b>\n\n"
                    "🔒 This bot is private."
                )

                return


            await message.reply_text(
                "👑 <b>VC TRACKER OWNER PANEL</b>\n\n"

                "🟢 <b>Bot is working!</b>\n\n"

                "🎙️ <b>Voice Chat Tracker</b>\n"
                "💾 MongoDB: ON\n"
                "📢 Log Channel: ON\n\n"

                "━━━━━━━━━━━━━━━━━━\n\n"

                "📌 <b>COMMANDS</b>\n\n"

                "➕ <code>/track</code>\n"
                "Track this group\n\n"

                "➖ <code>/stoptrack</code>\n"
                "Stop this group\n\n"

                "📊 <code>/status</code>\n"
                "Check current group\n\n"

                "📋 <code>/tracked</code>\n"
                "Show all tracked groups\n\n"

                "━━━━━━━━━━━━━━━━━━\n\n"

                "💡 <b>Use:</b>\n"
                "Jis group ka VC track karna hai,\n"
                "usi group me <code>/track</code> bhejo."
            )

            log.info(
                "START SUCCESS | owner=%s",
                user_id
            )

            return


        # ==================================================
        # OWNER ONLY COMMANDS
        # ==================================================

        if not owner:

            await message.reply_text(
                "❌ <b>Access Denied</b>"
            )

            return


        # ==================================================
        # /TRACK
        # ==================================================

        if command == "track":

            if message.chat.type not in (
                ChatType.GROUP,
                ChatType.SUPERGROUP
            ):

                await message.reply_text(
                    "❌ <b>/track group ke andar use karo.</b>\n\n"
                    "Jis group ka VC track karna hai, "
                    "usi group me command bhejo."
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

                "🟢 JOIN: ON\n"
                "🔴 LEAVE: ON\n"
                "💾 MongoDB: ON\n"
                "📢 Channel Logs: ON\n\n"

                "⚡ Ab is group ka VC track hoga."
            )


            log.info(
                "TRACK ENABLED | %s | %s",
                title,
                chat_id
            )

            return


        # ==================================================
        # /STOPTRACK
        # ==================================================

        if command == "stoptrack":

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
                    "⚠️ <b>Ye group tracking me nahi hai.</b>"
                )

                return


            await message.reply_text(
                "🛑 <b>VC TRACKING DISABLED</b>\n\n"
                f"🎙️ <b>Group:</b> {title}\n"
                f"🆔 <code>{chat_id}</code>"
            )


            log.info(
                "TRACK DISABLED | %s | %s",
                title,
                chat_id
            )

            return


        # ==================================================
        # /STATUS
        # ==================================================

        if command == "status":

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


            if is_tracked(chat_id):

                await message.reply_text(
                    "🟢 <b>TRACKING ACTIVE</b>\n\n"

                    f"🎙️ <b>Group:</b> {title}\n"
                    f"🆔 <code>{chat_id}</code>\n\n"

                    "🟢 JOIN: ON\n"
                    "🔴 LEAVE: ON\n"
                    "💾 MongoDB: ON\n"
                    "📢 Logs: ON"
                )

            else:

                await message.reply_text(
                    "🔴 <b>TRACKING OFF</b>\n\n"
                    f"🎙️ <b>Group:</b> {title}\n"
                    f"🆔 <code>{chat_id}</code>"
                )

            return


        # ==================================================
        # /TRACKED
        # ==================================================

        if command == "tracked":

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
                    f"🆔 <code>{group['chat_id']}</code>\n\n"
                )


            await message.reply_text(
                text
            )

            return


        # ==================================================
        # UNKNOWN COMMAND
        # ==================================================

        await message.reply_text(
            "❓ <b>Unknown Command</b>\n\n"

            "📌 Available commands:\n\n"

            "/start\n"
            "/track\n"
            "/stoptrack\n"
            "/status\n"
            "/tracked"
        )


    except Exception as e:

        log.exception(
            "BOT MESSAGE HANDLER ERROR: %s",
            e
        )

        try:

            await message.reply_text(
                "⚠️ <b>Internal Error</b>\n\n"
                "Command process karte waqt error aaya."
            )

        except Exception:

            pass


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

        # ------------------------------------------
        # GROUP CALL
        # ------------------------------------------

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


        # ------------------------------------------
        # PARTICIPANTS
        # ------------------------------------------

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
            "VC UPDATE ERROR: %s",
            e
        )


# ==================================================
# MAIN
# ==================================================

async def main():

    log.info(
        "=========================================="
    )

    log.info(
        "STARTING VC TRACKER"
    )

    log.info(
        "OWNER ID: %s",
        OWNER_ID
    )

    log.info(
        "=========================================="
    )


    # ------------------------------------------
    # BOT START
    # ------------------------------------------

    await bot.start()

    log.info(
        "BOT STARTED SUCCESSFULLY"
    )


    # ------------------------------------------
    # BOT INFO
    # ------------------------------------------

    bot_me = await bot.get_me()

    log.info(
        "BOT: @%s | ID: %s",
        bot_me.username,
        bot_me.id
    )


    # ------------------------------------------
    # USER START
    # ------------------------------------------

    await user.start()

    log.info(
        "USER SESSION STARTED SUCCESSFULLY"
    )


    user_me = await user.get_me()

    log.info(
        "TRACKING ACCOUNT: %s | ID: %s",
        user_me.first_name,
        user_me.id
    )


    # ------------------------------------------
    # STARTUP MESSAGE
    # ------------------------------------------

    try:

        await bot.send_message(
            OWNER_ID,

            "🟢 <b>VC TRACKER ONLINE</b>\n\n"

            "Bot successfully started.\n\n"

            "👉 Send <code>/start</code> "
            "to open Owner Panel."
        )


        log.info(
            "OWNER STARTUP MESSAGE SENT"
        )

    except Exception as e:

        log.exception(
            "OWNER STARTUP MESSAGE FAILED: %s",
            e
        )


    # ------------------------------------------
    # READY
    # ------------------------------------------

    log.info(
        "=========================================="
    )

    log.info(
        "VC TRACKER IS READY"
    )

    log.info(
        "WAITING FOR BOT COMMANDS..."
    )

    log.info(
        "=========================================="
    )


    await idle()


    # ------------------------------------------
    # STOP
    # ------------------------------------------

    log.info(
        "STOPPING VC TRACKER..."
    )


    await user.stop()

    await bot.stop()


# ==================================================
# RUN
# ==================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        log.info(
            "BOT STOPPED"
        )
import asyncio
import logging

from pyrogram import Client, idle
from pyrogram.raw import types

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    SESSION_STRING,
    LOG_CHANNEL
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
# LOG FUNCTION
# ==========================================

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


# ==========================================
# TRACKER
# ==========================================

tracker = VCTracker(
    user,
    send_log
)


# ==========================================
# RAW TELEGRAM UPDATES
# ==========================================

@user.on_raw_update()
async def raw_update(
    client,
    update,
    users,
    chats
):

    try:

        # ==================================
        # GROUP CALL CREATED / UPDATED
        # ==================================

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

            # Telegram channel ID
            # -> Pyrogram -100... chat ID

            chat_id = (
                -1000000000000
                - int(raw_chat_id)
            )

            await tracker.register_call(
                chat_id,
                call
            )

            # Voice chat ended
            if isinstance(
                call,
                types.GroupCallDiscarded
            ):

                tracker.end_call(call)

            return


        # ==================================
        # VC PARTICIPANT UPDATE
        # ==================================

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

            # Unknown call
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
# BOT COMMAND
# ==========================================

@bot.on_message()
async def bot_messages(
    client,
    message
):

    if message.text == "/start":

        await message.reply_text(
            "🎙️ <b>VC Tracker Bot</b>\n\n"
            "🟢 JOIN tracking: ON\n"
            "🔴 LEAVE tracking: ON\n"
            "💾 MongoDB: ON\n"
            "📢 Logs: ON\n\n"
            "⚡ VC Tracker is running."
        )


# ==========================================
# MAIN
# ==========================================

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

    # Start bot
    await bot.start()

    log.info(
        "Bot started successfully."
    )

    # Start user session
    await user.start()

    log.info(
        "User session started successfully."
    )

    # Check logged-in user
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

    # Keep both clients alive
    await idle()

    # Shutdown
    log.info(
        "Stopping VC Tracker..."
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
            "Bot stopped manually."
        )
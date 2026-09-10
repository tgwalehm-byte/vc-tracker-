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


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] "
           "[%(levelname)s] "
           "%(message)s"
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


async def send_log(text):

    try:

        await bot.send_message(
            chat_id=LOG_CHANNEL,
            text=text,
            disable_web_page_preview=True
        )

    except Exception as e:

        log.exception(
            "Could not send log: %s",
            e
        )


tracker = VCTracker(
    user,
    send_log
)


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

            chat_id = getattr(
                update,
                "chat_id",
                None
            )

            if chat_id is None:
                return

            # MTProto channel ID -> Pyrogram ID
            chat_id = (
                -1000000000000
                - int(chat_id)
            )

            await tracker.register_call(
                chat_id,
                call
            )

            if isinstance(
                call,
                types.GroupCallDiscarded
            ):

                tracker.call_ended(
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

            if call_id not in tracker.call_map:
                return

            for participant in update.participants:

                await tracker.process_participant(
                    call,
                    participant,
                    users
                )

    except Exception as e:

        log.exception(
            "Raw update error: %s",
            e
        )


@bot.on_message()
async def bot_messages(client, message):

    if message.text == "/start":

        await message.reply_text(
            "🎙️ <b>VC Tracker Bot</b>\n\n"
            "Voice Chat JOIN / LEAVE "
            "tracking is active."
        )


async def main():

    log.info("Starting VC Tracker...")

    await bot.start()

    log.info("Bot started.")

    await user.start()

    log.info("User session started.")

    try:

        me = await user.get_me()

        log.info(
            "Tracking account: %s (%s)",
            me.first_name,
            me.id
        )

    except Exception as e:

        log.warning(
            "Could not get user info: %s",
            e
        )

    await idle()

    await user.stop()
    await bot.stop()


if __name__ == "__main__":

    asyncio.run(main())
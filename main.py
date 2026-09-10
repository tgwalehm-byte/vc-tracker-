import asyncio
import json
import logging
import urllib.parse
import urllib.request
from html import escape

from pyrogram import Client, idle
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


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s"
)

log = logging.getLogger(__name__)


# =========================================================
# TELEGRAM BOT API
# =========================================================

BOT_API = (
    f"https://api.telegram.org/bot{BOT_TOKEN}"
)


def telegram_api_sync(
    method,
    params=None,
    timeout=40
):
    """
    Synchronous Telegram Bot API request.
    Runs through asyncio.to_thread().
    """

    if params is None:
        params = {}


    data = urllib.parse.urlencode(
        params
    ).encode()


    request = urllib.request.Request(
        f"{BOT_API}/{method}",
        data=data,
        method="POST"
    )


    with urllib.request.urlopen(
        request,
        timeout=timeout
    ) as response:

        raw = response.read().decode()

        return json.loads(raw)


async def telegram_api(
    method,
    params=None,
    timeout=40
):

    return await asyncio.to_thread(
        telegram_api_sync,
        method,
        params,
        timeout
    )


# =========================================================
# DELETE WEBHOOK
# =========================================================

async def delete_webhook():

    try:

        result = await telegram_api(
            "deleteWebhook",
            {
                "drop_pending_updates": "false"
            },
            timeout=20
        )


        if result.get("ok"):

            log.info(
                "Telegram webhook cleared."
            )

        else:

            log.error(
                "Webhook error: %s",
                result
            )

    except Exception as e:

        log.exception(
            "WEBHOOK ERROR: %s",
            e
        )


# =========================================================
# BOT INFO
# =========================================================

async def get_bot_info():

    result = await telegram_api(
        "getMe",
        {},
        timeout=20
    )


    if not result.get("ok"):

        raise RuntimeError(
            f"Telegram getMe failed: {result}"
        )


    return result["result"]


# =========================================================
# SEND MESSAGE
# =========================================================

async def send_message(
    chat_id,
    text,
    parse_mode="HTML"
):

    try:

        result = await telegram_api(
            "sendMessage",
            {
                "chat_id": str(chat_id),
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": "true"
            },
            timeout=30
        )


        if not result.get("ok"):

            log.error(
                "SEND MESSAGE FAILED: %s",
                result
            )

            return False


        return True


    except Exception as e:

        log.exception(
            "SEND MESSAGE ERROR: %s",
            e
        )

        return False


# =========================================================
# SEND LOG TO CHANNEL
# =========================================================

async def send_log(text):

    await send_message(
        LOG_CHANNEL,
        text
    )


# =========================================================
# PYROGRAM USER SESSION
# =========================================================

user = Client(
    "vc_tracker_user",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
    workers=20
)


# =========================================================
# VC TRACKER
# =========================================================

tracker = VCTracker(
    user,
    send_log
)


# =========================================================
# OWNER CHECK
# =========================================================

def is_owner(user_id):

    return (
        user_id is not None
        and int(user_id) == int(OWNER_ID)
    )


# =========================================================
# COMMAND PARSER
# =========================================================

def parse_command(text):

    if not text:
        return None


    text = text.strip()


    if not text.startswith("/"):
        return None


    first = text.split()[0]


    command = first[1:]


    if "@" in command:

        command = command.split(
            "@",
            1
        )[0]


    return command.lower()


# =========================================================
# HANDLE BOT COMMAND
# =========================================================

async def handle_command(
    message
):

    chat = message.get(
        "chat",
        {}
    )


    from_user = message.get(
        "from",
        {}
    )


    chat_id = chat.get(
        "id"
    )


    chat_type = chat.get(
        "type"
    )


    user_id = from_user.get(
        "id"
    )


    text = message.get(
        "text",
        ""
    )


    command = parse_command(
        text
    )


    log.info(
        "BOT UPDATE RECEIVED | "
        "user=%s | chat=%s | type=%s | command=%s",
        user_id,
        chat_id,
        chat_type,
        command
    )


    if not command:
        return


    # =====================================================
    # /START
    # =====================================================

    if command == "start":

        if not is_owner(user_id):

            await send_message(
                chat_id,
                "❌ <b>Access Denied</b>\n\n"
                "🔒 This bot is private."
            )

            return


        await send_message(
            chat_id,

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
            "Check current group\n\n"

            "📋 <code>/tracked</code>\n"
            "Show all tracked groups"
        )

        log.info(
            "START RESPONSE SENT"
        )

        return


    # =====================================================
    # OWNER ONLY
    # =====================================================

    if not is_owner(user_id):

        await send_message(
            chat_id,
            "❌ <b>Access Denied</b>"
        )

        return


    # =====================================================
    # /TRACK
    # =====================================================

    if command == "track":

        if chat_type not in (
            "group",
            "supergroup"
        ):

            await send_message(
                chat_id,

                "❌ <b>/track group ke andar use karo.</b>\n\n"
                "Jis group ka VC track karna hai, "
                "usi group me /track bhejo."
            )

            return


        title = (
            chat.get("title")
            or "Unknown Group"
        )


        if is_tracked(chat_id):

            await send_message(
                chat_id,

                "⚠️ <b>Already Tracking</b>\n\n"
                f"🎙️ <b>Group:</b> "
                f"{escape(title)}\n"
                f"🆔 <code>{chat_id}</code>"
            )

            return


        add_tracked_group(
            chat_id=chat_id,
            title=title,
            added_by=OWNER_ID
        )


        await send_message(
            chat_id,

            "✅ <b>VC TRACKING ENABLED</b>\n\n"

            f"🎙️ <b>Group:</b> "
            f"{escape(title)}\n"

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


    # =====================================================
    # /STOPTRACK
    # =====================================================

    if command == "stoptrack":

        if chat_type not in (
            "group",
            "supergroup"
        ):

            await send_message(
                chat_id,
                "❌ Group ke andar /stoptrack use karo."
            )

            return


        title = (
            chat.get("title")
            or "Unknown Group"
        )


        removed = remove_tracked_group(
            chat_id
        )


        if not removed:

            await send_message(
                chat_id,
                "⚠️ Ye group tracking me nahi hai."
            )

            return


        await send_message(
            chat_id,

            "🛑 <b>VC TRACKING DISABLED</b>\n\n"

            f"🎙️ <b>Group:</b> "
            f"{escape(title)}"
        )


        log.info(
            "TRACK DISABLED | %s | %s",
            title,
            chat_id
        )

        return


    # =====================================================
    # /STATUS
    # =====================================================

    if command == "status":

        if chat_type not in (
            "group",
            "supergroup"
        ):

            await send_message(
                chat_id,
                "❌ Group ke andar /status use karo."
            )

            return


        title = (
            chat.get("title")
            or "Unknown Group"
        )


        if is_tracked(chat_id):

            await send_message(
                chat_id,

                "🟢 <b>TRACKING ACTIVE</b>\n\n"

                f"🎙️ <b>Group:</b> "
                f"{escape(title)}\n"

                f"🆔 <code>{chat_id}</code>\n\n"

                "🟢 JOIN: ON\n"
                "🔴 LEAVE: ON\n"
                "💾 MongoDB: ON\n"
                "📢 Logs: ON"
            )

        else:

            await send_message(
                chat_id,

                "🔴 <b>TRACKING OFF</b>\n\n"

                f"🎙️ <b>Group:</b> "
                f"{escape(title)}"
            )

        return


    # =====================================================
    # /TRACKED
    # =====================================================

    if command == "tracked":

        groups = get_tracked_groups()


        if not groups:

            await send_message(
                chat_id,
                "📋 <b>No tracked groups.</b>"
            )

            return


        text = (
            "📋 <b>TRACKED GROUPS</b>\n\n"
        )


        for number, group in enumerate(
            groups,
            1
        ):

            title = escape(
                group.get(
                    "title",
                    "Unknown"
                )
            )


            text += (
                f"{number}. 🎙️ "
                f"<b>{title}</b>\n"
                f"🆔 <code>"
                f"{group['chat_id']}"
                f"</code>\n\n"
            )


        await send_message(
            chat_id,
            text
        )

        return


    # =====================================================
    # UNKNOWN COMMAND
    # =====================================================

    await send_message(
        chat_id,

        "❓ <b>Unknown Command</b>\n\n"

        "/start\n"
        "/track\n"
        "/stoptrack\n"
        "/status\n"
        "/tracked"
    )


# =========================================================
# BOT API LONG POLLING
# =========================================================

async def bot_polling():

    offset = 0


    log.info(
        "Bot API polling started."
    )


    while True:

        try:

            result = await telegram_api(
                "getUpdates",
                {
                    "offset": str(offset),
                    "timeout": "25",
                    "allowed_updates": json.dumps(
                        ["message"]
                    )
                },
                timeout=35
            )


            if not result.get("ok"):

                log.error(
                    "getUpdates failed: %s",
                    result
                )

                await asyncio.sleep(5)

                continue


            updates = result.get(
                "result",
                []
            )


            for update in updates:

                update_id = update.get(
                    "update_id"
                )


                if update_id is not None:

                    offset = (
                        int(update_id) + 1
                    )


                message = update.get(
                    "message"
                )


                if not message:
                    continue


                await handle_command(
                    message
                )


        except asyncio.CancelledError:

            log.info(
                "Bot polling stopped."
            )

            raise


        except Exception as e:

            log.exception(
                "BOT POLLING ERROR: %s",
                e
            )

            await asyncio.sleep(5)


# =========================================================
# RAW VC UPDATES
# =========================================================

@user.on_raw_update()
async def raw_update(
    client,
    update,
    users,
    chats
):

    try:

        # -------------------------------------------------
        # GROUP CALL
        # -------------------------------------------------

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


            if not is_tracked(
                chat_id
            ):

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


        # -------------------------------------------------
        # PARTICIPANTS
        # -------------------------------------------------

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


    except Exception:

        log.exception(
            "VC UPDATE ERROR"
        )


# =========================================================
# MAIN
# =========================================================

async def main():

    log.info(
        "=========================================="
    )

    log.info(
        "VC TRACKER STARTING"
    )

    log.info(
        "OWNER_ID = %s",
        OWNER_ID
    )

    log.info(
        "=========================================="
    )


    # -----------------------------------------------------
    # TELEGRAM BOT API
    # -----------------------------------------------------

    await delete_webhook()


    bot_info = await get_bot_info()


    log.info(
        "BOT API CONNECTED"
    )

    log.info(
        "BOT = @%s | ID = %s",
        bot_info.get("username"),
        bot_info.get("id")
    )


    # -----------------------------------------------------
    # START USER SESSION
    # -----------------------------------------------------

    await user.start()


    log.info(
        "USER SESSION STARTED SUCCESSFULLY"
    )


    user_info = await user.get_me()


    log.info(
        "USER SESSION = %s | ID = %s",
        user_info.first_name,
        user_info.id
    )


    # -----------------------------------------------------
    # START POLLING
    # -----------------------------------------------------

    polling_task = asyncio.create_task(
        bot_polling()
    )


    # -----------------------------------------------------
    # STARTUP MESSAGE
    # -----------------------------------------------------

    await send_message(
        OWNER_ID,

        "🟢 <b>VC TRACKER ONLINE</b>\n\n"

        f"🤖 <b>Bot:</b> "
        f"@{escape(bot_info.get('username', 'unknown'))}\n"

        f"👑 <b>Owner ID:</b> "
        f"<code>{OWNER_ID}</code>\n\n"

        "📡 Bot API polling: ON\n"
        "🎙️ VC tracking: ON\n"
        "💾 MongoDB: ON\n\n"

        "👉 Send <code>/start</code>"
    )


    log.info(
        "OWNER STARTUP MESSAGE SENT"
    )


    log.info(
        "=========================================="
    )

    log.info(
        "BOT IS READY"
    )

    log.info(
        "WAITING FOR BOT API UPDATES..."
    )

    log.info(
        "=========================================="
    )


    try:

        await idle()


    finally:

        polling_task.cancel()


        try:

            await polling_task

        except asyncio.CancelledError:

            pass


        await user.stop()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        log.info(
            "BOT STOPPED"
        )
# ============================================================
# VC TRACKER BOT
# Telegram Voice Chat JOIN / LEAVE Tracker
# ============================================================

import asyncio
import json
import logging
import urllib.parse
import urllib.request

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
    get_tracked_groups,
    get_active_for_chat
)

from tracker import VCTracker


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s"
)

log = logging.getLogger("VC-TRACKER")


# ============================================================
# TELEGRAM BOT API
# ============================================================

BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def telegram_api_sync(method, data=None, timeout=30):

    if data is None:
        data = {}

    url = f"{BOT_API}/{method}"

    encoded = urllib.parse.urlencode(data).encode()

    request = urllib.request.Request(
        url,
        data=encoded,
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
    data=None,
    timeout=30
):

    loop = asyncio.get_running_loop()

    return await loop.run_in_executor(
        None,
        lambda: telegram_api_sync(
            method,
            data,
            timeout
        )
    )


# ============================================================
# SEND MESSAGE
# ============================================================

async def send_message(
    chat_id,
    text,
    reply_to=None
):

    data = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true"
    }

    if reply_to:
        data["reply_to_message_id"] = str(reply_to)

    try:

        result = await telegram_api(
            "sendMessage",
            data
        )

        if not result.get("ok"):

            log.error(
                "sendMessage failed: %s",
                result
            )

            return False

        return True

    except Exception as e:

        log.exception(
            "sendMessage ERROR: %s",
            e
        )

        return False


# ============================================================
# LOG CHANNEL
# ============================================================

async def send_log(text):

    log.info(
        "Sending log to channel..."
    )

    result = await send_message(
        LOG_CHANNEL,
        text
    )

    if result:

        log.info(
            "LOG CHANNEL MESSAGE SENT"
        )

    else:

        log.error(
            "FAILED TO SEND LOG CHANNEL MESSAGE"
        )


# ============================================================
# BOT INFO
# ============================================================

async def get_bot_info():

    try:

        result = await telegram_api(
            "getMe"
        )

        if not result.get("ok"):

            raise RuntimeError(
                str(result)
            )

        return result["result"]

    except Exception as e:

        log.exception(
            "Bot API getMe failed: %s",
            e
        )

        return None


# ============================================================
# DELETE WEBHOOK
# ============================================================

async def delete_webhook():

    try:

        result = await telegram_api(
            "deleteWebhook",
            {
                "drop_pending_updates": "false"
            }
        )

        log.info(
            "deleteWebhook: %s",
            result
        )

    except Exception as e:

        log.exception(
            "deleteWebhook ERROR: %s",
            e
        )


# ============================================================
# COMMAND PARSER
# ============================================================

def parse_command(text):

    if not text:
        return None, None

    if not text.startswith("/"):
        return None, None

    parts = text.split()

    command = parts[0]

    if "@" in command:

        command = command.split(
            "@",
            1
        )[0]

    command = command.lower()

    args = parts[1:]

    return command, args


# ============================================================
# CHECK ADMIN
# ============================================================

async def is_group_admin(
    user_client,
    chat_id,
    user_id
):

    try:

        member = await user_client.get_chat_member(
            chat_id,
            user_id
        )

        status = str(
            getattr(
                member,
                "status",
                ""
            )
        ).lower()

        return status in (
            "administrator",
            "owner"
        )

    except Exception as e:

        log.warning(
            "Admin check failed | chat=%s | user=%s | %s",
            chat_id,
            user_id,
            e
        )

        return False


# ============================================================
# /START
# ============================================================

async def command_start(
    chat_id,
    user_id,
    message_id
):

    text = (
        "🟢 <b>VC TRACKER BOT</b>\n\n"

        "Welcome! 👋\n\n"

        "I can track Telegram Voice Chat "
        "<b>JOIN / LEAVE</b> activity.\n\n"

        "📌 <b>Commands</b>\n\n"

        "➕ <code>/track</code> — Track this group\n"
        "➖ <code>/stoptrack</code> — Stop tracking\n"
        "📊 <code>/status</code> — Current VC status\n"
        "📋 <code>/tracked</code> — Tracked groups\n\n"

        "⚡ <b>Fast VC Tracking</b>\n"
        "🗄️ MongoDB Storage\n"
        "📢 Channel Logs"
    )

    await send_message(
        chat_id,
        text,
        message_id
    )


# ============================================================
# /TRACK
# ============================================================

async def command_track(
    user_client,
    chat_id,
    user_id,
    message_id
):

    # Private chat
    if chat_id > 0:

        await send_message(
            chat_id,
            "❌ <b>/track</b> group ke andar use karo.",
            message_id
        )

        return

    # Owner can always track
    if user_id != OWNER_ID:

        admin = await is_group_admin(
            user_client,
            chat_id,
            user_id
        )

        if not admin:

            await send_message(
                chat_id,
                "❌ Sirf <b>Group Owner/Admin</b> "
                "ya bot owner ye command use kar sakta hai.",
                message_id
            )

            return

    try:

        chat = await user_client.get_chat(
            chat_id
        )

        title = (
            getattr(
                chat,
                "title",
                None
            )
            or "Unknown Group"
        )

    except Exception:

        title = "Unknown Group"

    add_tracked_group(
        chat_id=chat_id,
        title=title,
        added_by=user_id
    )

    log.info(
        "GROUP TRACKED | %s | %s",
        chat_id,
        title
    )

    await send_message(
        chat_id,
        (
            "✅ <b>VC TRACKING ENABLED</b>\n\n"
            f"🎙️ <b>Group:</b> {title}\n"
            f"🆔 <b>ID:</b> <code>{chat_id}</code>\n\n"
            "Ab is group ke VC me hone wale "
            "<b>JOIN / LEAVE</b> track honge.\n\n"
            "📢 Logs designated channel me jayenge."
        ),
        message_id
    )


# ============================================================
# /STOPTRACK
# ============================================================

async def command_stoptrack(
    user_client,
    chat_id,
    user_id,
    message_id
):

    if chat_id > 0:

        await send_message(
            chat_id,
            "❌ Group ke andar command use karo.",
            message_id
        )

        return

    if user_id != OWNER_ID:

        admin = await is_group_admin(
            user_client,
            chat_id,
            user_id
        )

        if not admin:

            await send_message(
                chat_id,
                "❌ Sirf Group Admin/Owner use kar sakta hai.",
                message_id
            )

            return

    removed = remove_tracked_group(
        chat_id
    )

    if removed:

        text = (
            "🛑 <b>VC TRACKING DISABLED</b>\n\n"
            f"🆔 <b>Group:</b> <code>{chat_id}</code>\n\n"
            "Is group ki VC tracking ab band hai."
        )

    else:

        text = (
            "ℹ️ Ye group currently track nahi ho raha."
        )

    await send_message(
        chat_id,
        text,
        message_id
    )


# ============================================================
# /STATUS
# ============================================================

async def command_status(
    user_client,
    chat_id,
    message_id
):

    if chat_id > 0:

        await send_message(
            chat_id,
            "❌ Ye command group me use karo.",
            message_id
        )

        return

    tracked = is_tracked(
        chat_id
    )

    active = get_active_for_chat(
        chat_id
    )

    try:

        chat = await user_client.get_chat(
            chat_id
        )

        title = (
            getattr(
                chat,
                "title",
                None
            )
            or "Unknown Group"
        )

    except Exception:

        title = "Unknown Group"

    status = (
        "🟢 <b>TRACKING ACTIVE</b>"
        if tracked
        else
        "🔴 <b>TRACKING OFF</b>"
    )

    text = (
        "📊 <b>VC TRACKER STATUS</b>\n\n"

        f"🎙️ <b>Group:</b> {title}\n"
        f"🆔 <b>ID:</b> <code>{chat_id}</code>\n\n"

        f"📡 <b>Status:</b> {status}\n"
        f"👥 <b>Active Sessions:</b> {len(active)}"
    )

    if active:

        text += "\n\n<b>Currently in VC:</b>\n"

        for session in active[:20]:

            name = session.get(
                "name",
                "Unknown"
            )

            user_id = session.get(
                "user_id"
            )

            text += (
                f"• {name} "
                f"<code>{user_id}</code>\n"
            )

    await send_message(
        chat_id,
        text,
        message_id
    )


# ============================================================
# /TRACKED
# ============================================================

async def command_tracked(
    chat_id,
    message_id
):

    groups = get_tracked_groups()

    if not groups:

        await send_message(
            chat_id,
            "📋 <b>No groups are being tracked.</b>",
            message_id
        )

        return

    text = (
        "📋 <b>TRACKED GROUPS</b>\n\n"
    )

    for index, group in enumerate(
        groups,
        1
    ):

        title = group.get(
            "title",
            "Unknown"
        )

        group_id = group.get(
            "chat_id"
        )

        text += (
            f"{index}. 🎙️ <b>{title}</b>\n"
            f"   🆔 <code>{group_id}</code>\n\n"
        )

    await send_message(
        chat_id,
        text,
        message_id
    )


# ============================================================
# HANDLE BOT UPDATE
# ============================================================

async def handle_bot_update(
    update,
    user_client
):

    message = update.get(
        "message"
    )

    if not message:
        return

    text = message.get(
        "text"
    )

    if not text:
        return

    from_user = message.get(
        "from"
    )

    if not from_user:
        return

    user_id = from_user.get(
        "id"
    )

    chat = message.get(
        "chat"
    )

    if not chat:
        return

    chat_id = chat.get(
        "id"
    )

    message_id = message.get(
        "message_id"
    )

    command, args = parse_command(
        text
    )

    if not command:
        return

    log.info(
        "COMMAND RECEIVED | %s | user=%s | chat=%s",
        command,
        user_id,
        chat_id
    )

    # ==========================
    # START
    # ==========================

    if command == "/start":

        await command_start(
            chat_id,
            user_id,
            message_id
        )

        return

    # ==========================
    # TRACK
    # ==========================

    if command == "/track":

        await command_track(
            user_client,
            chat_id,
            user_id,
            message_id
        )

        return

    # ==========================
    # STOP TRACK
    # ==========================

    if command == "/stoptrack":

        await command_stoptrack(
            user_client,
            chat_id,
            user_id,
            message_id
        )

        return

    # ==========================
    # STATUS
    # ==========================

    if command == "/status":

        await command_status(
            user_client,
            chat_id,
            message_id
        )

        return

    # ==========================
    # TRACKED
    # ==========================

    if command == "/tracked":

        await command_tracked(
            chat_id,
            message_id
        )

        return


# ============================================================
# BOT API LONG POLLING
# ============================================================

async def bot_polling(
    user_client
):

    log.info(
        "Bot API polling started."
    )

    offset = 0

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

                await asyncio.sleep(3)

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

                    offset = update_id + 1

                log.info(
                    "BOT UPDATE RECEIVED | update_id=%s",
                    update_id
                )

                try:

                    await handle_bot_update(
                        update,
                        user_client
                    )

                except Exception as e:

                    log.exception(
                        "BOT UPDATE ERROR: %s",
                        e
                    )

        except asyncio.CancelledError:

            log.info(
                "Bot polling cancelled."
            )

            break

        except Exception as e:

            log.exception(
                "BOT POLLING ERROR: %s",
                e
            )

            await asyncio.sleep(3)


# ============================================================
# MAIN
# ============================================================

async def main():

    log.info(
        "=========================================="
    )

    log.info(
        "        VC TRACKER STARTING"
    )

    log.info(
        "=========================================="
    )

    # --------------------------------------------------------
    # Remove webhook
    # --------------------------------------------------------

    await delete_webhook()

    # --------------------------------------------------------
    # Check Bot API
    # --------------------------------------------------------

    bot_info = await get_bot_info()

    if not bot_info:

        log.error(
            "BOT API CONNECTION FAILED"
        )

        return

    bot_username = bot_info.get(
        "username",
        "unknown"
    )

    bot_id = bot_info.get(
        "id",
        "unknown"
    )

    log.info(
        "BOT API CONNECTED | ID=%s | USERNAME=@%s",
        bot_id,
        bot_username
    )

    # --------------------------------------------------------
    # User Pyrogram Client
    # --------------------------------------------------------

    user = Client(
        "vc_tracker_user",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION_STRING,
        workers=20
    )

    # --------------------------------------------------------
    # Tracker
    # --------------------------------------------------------

    tracker = VCTracker(
        user,
        send_log
    )

    # --------------------------------------------------------
    # RAW MTProto UPDATE HANDLER
    # --------------------------------------------------------

    @user.on_raw_update()
    async def raw_update_handler(
        client,
        update,
        users,
        chats
    ):

        try:

            log.info(
                "RAW UPDATE RECEIVED | %s",
                type(update).__name__
            )

            # ------------------------------
            # Voice Chat Created / Updated
            # ------------------------------

            if isinstance(
                update,
                types.UpdateGroupCall
            ):

                raw_chat_id = getattr(
                    update,
                    "chat_id",
                    None
                )

                call = getattr(
                    update,
                    "call",
                    None
                )

                if raw_chat_id is None:

                    log.warning(
                        "UpdateGroupCall has no chat_id"
                    )

                    return

                chat_id = (
                    -1000000000000
                    - int(raw_chat_id)
                )

                log.info(
                    "RAW VC UPDATE | "
                    "raw_chat=%s | chat=%s",
                    raw_chat_id,
                    chat_id
                )

                await tracker.register_call(
                    chat_id,
                    call
                )

                return

            # ------------------------------
            # Voice Chat Participants
            # ------------------------------

            if isinstance(
                update,
                types.UpdateGroupCallParticipants
            ):

                call = getattr(
                    update,
                    "call",
                    None
                )

                participants = getattr(
                    update,
                    "participants",
                    []
                )

                call_id = getattr(
                    call,
                    "id",
                    None
                )

                log.info(
                    "RAW VC PARTICIPANTS | "
                    "call=%s | participants=%s",
                    call_id,
                    len(participants)
                )

                await tracker.participant_batch(
                    call,
                    participants,
                    users
                ) if hasattr(
                    tracker,
                    "participant_batch"
                ) else await process_participants(
                    tracker,
                    call,
                    participants,
                    users
                )

                return

        except Exception as e:

            log.exception(
                "RAW UPDATE HANDLER ERROR: %s",
                e
            )

    # --------------------------------------------------------
    # START USER SESSION
    # --------------------------------------------------------

    await user.start()

    me = await user.get_me()

    log.info(
        "USER SESSION STARTED SUCCESSFULLY"
    )

    log.info(
        "USER SESSION = %s | ID = %s | USERNAME = @%s",
        me.first_name or "User",
        me.id,
        me.username or "none"
    )

    # --------------------------------------------------------
    # Startup log
    # --------------------------------------------------------

    await send_log(
        (
            "🟢 <b>VC TRACKER ONLINE</b>\n\n"
            "Bot successfully started.\n\n"
            f"🤖 <b>Bot:</b> @{bot_username}\n"
            f"👤 <b>User Session:</b> {me.id}\n\n"
            "📡 VC tracking system is ready."
        )
    )

    log.info(
        "OWNER STARTUP MESSAGE SENT"
    )

    # --------------------------------------------------------
    # Start Bot API polling
    # --------------------------------------------------------

    polling_task = asyncio.create_task(
        bot_polling(user)
    )

    log.info(
        "BOT IS READY"
    )

    log.info(
        "WAITING FOR INCOMING UPDATES..."
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

        log.info(
            "USER SESSION STOPPED"
        )


# ============================================================
# PARTICIPANT FALLBACK
# ============================================================

async def process_participants(
    tracker,
    call,
    participants,
    users
):

    for participant in participants:

        try:

            await tracker.participant(
                call,
                participant,
                users
            )

        except Exception as e:

            log.exception(
                "PARTICIPANT ERROR: %s",
                e
            )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        log.info(
            "Bot stopped manually."
        )

    except Exception as e:

        log.exception(
            "FATAL ERROR: %s",
            e
        )
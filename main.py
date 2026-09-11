import asyncio
import json
import logging
import urllib.parse
import urllib.request

from pyrogram import Client, idle

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    SESSION_STRING,
    LOG_CHANNEL,
    OWNER_ID,
)

from database import (
    add_tracked_group,
    remove_tracked_group,
    is_tracked,
    get_tracked_groups,
    get_active_for_chat,
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
# BOT API
# ============================================================

BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def telegram_api_sync(
    method,
    data=None,
    timeout=30
):

    if data is None:
        data = {}

    request = urllib.request.Request(
        f"{BOT_API}/{method}",
        data=urllib.parse.urlencode(
            data
        ).encode(),
        method="POST"
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout
    ) as response:

        return json.loads(
            response.read().decode()
        )


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
        "disable_web_page_preview": "true",
    }

    if reply_to:

        data[
            "reply_to_message_id"
        ] = str(reply_to)

    try:

        result = await telegram_api(
            "sendMessage",
            data
        )

        if not result.get("ok"):

            log.error(
                "SEND MESSAGE FAILED | %s",
                result
            )

            return False

        return True

    except Exception as e:

        log.exception(
            "SEND MESSAGE ERROR | %s",
            e
        )

        return False


async def send_log(text):

    return await send_message(
        LOG_CHANNEL,
        text
    )


# ============================================================
# BOT INFO
# ============================================================

async def get_bot_info():

    try:

        result = await telegram_api(
            "getMe"
        )

        if result.get("ok"):

            return result[
                "result"
            ]

    except Exception as e:

        log.exception(
            "GET ME ERROR | %s",
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
            "WEBHOOK | %s",
            result
        )

    except Exception as e:

        log.exception(
            "WEBHOOK ERROR | %s",
            e
        )


# ============================================================
# COMMAND PARSER
# ============================================================

def parse_command(text):

    if not text or not text.startswith("/"):
        return None, []

    parts = text.split()

    command = parts[0]

    if "@" in command:

        command = command.split(
            "@",
            1
        )[0]

    return (
        command.lower(),
        parts[1:]
    )


# ============================================================
# ADMIN CHECK
# ============================================================

async def is_group_admin(
    user,
    chat_id,
    user_id
):

    try:

        member = await user.get_chat_member(
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

        # Pyrogram status kabhi:
        # administrator / owner
        # ya ChatMemberStatus.ADMINISTRATOR
        if (
            status == "administrator"
            or status == "owner"
            or status.endswith(
                ".administrator"
            )
            or status.endswith(
                ".owner"
            )
        ):
            return True

        return False

    except Exception as e:

        log.warning(
            "ADMIN CHECK ERROR | "
            "group=%s | user=%s | %s",
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
    message_id
):

    await send_message(
        chat_id,
        (
            "🟢 <b>VC TRACKER</b>\n\n"

            "🎙️ Voice Chat JOIN / LEAVE Tracker\n\n"

            "➕ <code>/track</code>\n"
            "➖ <code>/stoptrack</code>\n"
            "📊 <code>/status</code>\n"
            "📋 <code>/tracked</code>"
        ),
        message_id
    )


# ============================================================
# /TRACK
# ============================================================

async def command_track(
    user,
    chat_id,
    user_id,
    message_id
):

    if chat_id > 0:

        await send_message(
            chat_id,
            "❌ Group ke andar /track use karo.",
            message_id
        )

        return

    if user_id != OWNER_ID:

        if not await is_group_admin(
            user,
            chat_id,
            user_id
        ):

            await send_message(
                chat_id,
                "❌ Admin/Owner only.",
                message_id
            )

            return

    try:

        chat = await user.get_chat(
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
        chat_id,
        title,
        user_id
    )

    await send_message(
        chat_id,
        (
            "✅ <b>VC TRACKING ON</b>\n\n"

            f"🎙️ <b>{title}</b>\n\n"

            "👑 Owner: TRACKED\n"
            "👮 Admin: TRACKED\n"
            "👤 Member: TRACKED\n\n"

            "VC JOIN/LEAVE logs channel me jayenge."
        ),
        message_id
    )

    log.info(
        "TRACK ENABLED | group=%s | title=%s",
        chat_id,
        title
    )


# ============================================================
# /STOPTRACK
# ============================================================

async def command_stoptrack(
    user,
    chat_id,
    user_id,
    message_id
):

    if chat_id > 0:
        return

    if user_id != OWNER_ID:

        if not await is_group_admin(
            user,
            chat_id,
            user_id
        ):

            await send_message(
                chat_id,
                "❌ Admin/Owner only.",
                message_id
            )

            return

    removed = remove_tracked_group(
        chat_id
    )

    await send_message(
        chat_id,
        (
            "🛑 <b>VC TRACKING OFF</b>"
            if removed
            else
            "ℹ️ Group already OFF."
        ),
        message_id
    )

    log.info(
        "TRACK DISABLED | group=%s",
        chat_id
    )


# ============================================================
# /STATUS
# ============================================================

async def command_status(
    user,
    chat_id,
    message_id
):

    if chat_id > 0:
        return

    active = get_active_for_chat(
        chat_id
    )

    status = (
        "🟢 ON"
        if is_tracked(chat_id)
        else
        "🔴 OFF"
    )

    await send_message(
        chat_id,
        (
            "📊 <b>VC STATUS</b>\n\n"

            f"📡 Tracking: {status}\n"
            f"👥 Active VC Users: {len(active)}"
        ),
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
            "📋 No tracked groups.",
            message_id
        )

        return

    text = (
        "📋 <b>TRACKED GROUPS</b>\n\n"
    )

    for group in groups:

        title = group.get(
            "title",
            "Unknown Group"
        )

        group_id = group.get(
            "chat_id"
        )

        text += (
            f"🎙️ <b>{title}</b>\n"
            f"🆔 <code>{group_id}</code>\n\n"
        )

    await send_message(
        chat_id,
        text,
        message_id
    )


# ============================================================
# HANDLE BOT UPDATE
# ============================================================

async def handle_update(
    update,
    user
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

    sender = message.get(
        "from"
    )

    chat = message.get(
        "chat"
    )

    if not sender or not chat:
        return

    user_id = sender.get(
        "id"
    )

    chat_id = chat.get(
        "id"
    )

    message_id = message.get(
        "message_id"
    )

    command, args = parse_command(
        text
    )

    if command == "/start":

        await command_start(
            chat_id,
            message_id
        )

    elif command == "/track":

        await command_track(
            user,
            chat_id,
            user_id,
            message_id
        )

    elif command == "/stoptrack":

        await command_stoptrack(
            user,
            chat_id,
            user_id,
            message_id
        )

    elif command == "/status":

        await command_status(
            user,
            chat_id,
            message_id
        )

    elif command == "/tracked":

        await command_tracked(
            chat_id,
            message_id
        )


# ============================================================
# BOT POLLING
# ============================================================

async def bot_polling(
    user
):

    offset = 0

    log.info(
        "🤖 BOT POLLING STARTED"
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
                    "GET UPDATES FAILED | %s",
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

                    offset = (
                        update_id + 1
                    )

                try:

                    await handle_update(
                        update,
                        user
                    )

                except Exception as e:

                    log.exception(
                        "COMMAND ERROR | %s",
                        e
                    )

        except asyncio.CancelledError:

            log.info(
                "BOT POLLING STOPPED"
            )

            return

        except Exception as e:

            log.exception(
                "POLLING ERROR | %s",
                e
            )

            await asyncio.sleep(
                3
            )


# ============================================================
# MAIN
# ============================================================

async def main():

    # --------------------------------------------------------
    # WEBHOOK
    # --------------------------------------------------------

    await delete_webhook()

    # --------------------------------------------------------
    # BOT CHECK
    # --------------------------------------------------------

    bot_info = await get_bot_info()

    if not bot_info:

        log.error(
            "❌ BOT API NOT CONNECTED"
        )

        return

    log.info(
        "🤖 BOT API CONNECTED | @%s",
        bot_info.get(
            "username"
        )
    )

    # --------------------------------------------------------
    # USER CLIENT
    # --------------------------------------------------------

    user = Client(
        "vc_tracker_user",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION_STRING,
        workers=50
    )

    # --------------------------------------------------------
    # TRACKER
    # --------------------------------------------------------

    tracker = VCTracker(
        user,
        send_log
    )

    # ========================================================
    # RAW UPDATE HANDLER
    # ========================================================

    @user.on_raw_update()
    async def raw_update_handler(
        client,
        update,
        users,
        chats
    ):

        try:

            update_name = (
                type(update).__name__
            )

            # ------------------------------------------------
            # EVERY RAW UPDATE
            # ------------------------------------------------

            log.info(
                "🔥 RAW UPDATE RECEIVED: %s",
                update_name
            )

            # ------------------------------------------------
            # VC UPDATE
            # ------------------------------------------------

            if update_name in (
                "UpdateGroupCall",
                "UpdateGroupCallParticipants",
            ):

                log.info(
                    "🎙️ VC UPDATE RECEIVED: %s",
                    update_name
                )

                log.info(
                    "VC UPDATE DATA: %s",
                    update
                )

            # ------------------------------------------------
            # SEND TO TRACKER
            # ------------------------------------------------

            await tracker.raw_update(
                update,
                users,
                chats
            )

        except Exception as e:

            log.exception(
                "❌ RAW UPDATE HANDLER ERROR | %s",
                e
            )

    # ========================================================
    # START USER SESSION
    # ========================================================

    await user.start()

    me = await user.get_me()

    log.info(
        "======================================"
    )

    log.info(
        "👤 USER SESSION STARTED"
    )

    log.info(
        "USER ID: %s",
        me.id
    )

    log.info(
        "USERNAME: @%s",
        me.username or "none"
    )

    log.info(
        "======================================"
    )

    # ========================================================
    # START TRACKER
    # ========================================================

    await tracker.start()

    # ========================================================
    # ONLINE LOG
    # ========================================================

    await send_log(
        (
            "🟢 <b>VC TRACKER ONLINE</b>\n\n"

            f"🤖 Bot: "
            f"@{bot_info.get('username')}\n"

            f"👤 User Session: "
            f"<code>{me.id}</code>\n\n"

            "🎙️ VC Tracking: READY\n"
            "📡 Raw Updates: READY\n"
            "🔄 Auto Discovery: READY\n"
            "🗄️ MongoDB: READY"
        )
    )

    # ========================================================
    # BOT POLLING
    # ========================================================

    polling_task = asyncio.create_task(
        bot_polling(
            user
        )
    )

    log.info(
        "======================================"
    )

    log.info(
        "✅ BOT IS READY"
    )

    log.info(
        "👀 WAITING FOR VC UPDATES..."
    )

    log.info(
        "======================================"
    )

    # ========================================================
    # RUN
    # ========================================================

    try:

        await idle()

    finally:

        # ----------------------------------------------------
        # STOP POLLING
        # ----------------------------------------------------

        polling_task.cancel()

        try:

            await polling_task

        except asyncio.CancelledError:

            pass

        # ----------------------------------------------------
        # STOP TRACKER
        # ----------------------------------------------------

        try:

            await tracker.stop()

        except Exception as e:

            log.exception(
                "TRACKER STOP ERROR | %s",
                e
            )

        # ----------------------------------------------------
        # STOP USER CLIENT
        # ----------------------------------------------------

        try:

            await user.stop()

        except Exception as e:

            log.exception(
                "USER CLIENT STOP ERROR | %s",
                e
            )

        log.info(
            "🛑 VC TRACKER STOPPED"
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
            "BOT STOPPED"
        )

    except Exception as e:

        log.exception(
            "FATAL ERROR | %s",
            e
        )
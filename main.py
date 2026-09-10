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

    url = f"{BOT_API}/{method}"

    encoded = urllib.parse.urlencode(
        data
    ).encode()

    request = urllib.request.Request(
        url,
        data=encoded,
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


# ============================================================
# SEND LOG TO CHANNEL
# ============================================================

async def send_log(text):

    log.info(
        "SENDING LOG TO CHANNEL"
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
            "LOG CHANNEL MESSAGE FAILED"
        )


# ============================================================
# BOT INFORMATION
# ============================================================

async def get_bot_info():

    try:

        result = await telegram_api(
            "getMe"
        )

        if not result.get("ok"):
            return None

        return result.get(
            "result"
        )

    except Exception as e:

        log.exception(
            "GET BOT INFO ERROR | %s",
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
            "WEBHOOK REMOVED | %s",
            result
        )

    except Exception as e:

        log.exception(
            "DELETE WEBHOOK ERROR | %s",
            e
        )


# ============================================================
# COMMAND PARSER
# ============================================================

def parse_command(text):

    if not text:
        return None, []

    if not text.startswith("/"):
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
            "ADMIN CHECK ERROR | %s",
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

    text = (
        "🟢 <b>VC TRACKER BOT</b>\n\n"

        "Welcome! 👋\n\n"

        "🎙️ <b>Voice Chat JOIN / LEAVE Tracker</b>\n\n"

        "📌 <b>Commands</b>\n\n"

        "➕ <code>/track</code> — Track group\n"
        "➖ <code>/stoptrack</code> — Stop tracking\n"
        "📊 <code>/status</code> — VC status\n"
        "📋 <code>/tracked</code> — Tracked groups\n\n"

        "⚡ Fast Processing\n"
        "🗄️ MongoDB\n"
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

    if chat_id > 0:

        await send_message(
            chat_id,
            "❌ <b>/track</b> group ke andar use karo.",
            message_id
        )

        return

    # Owner can always use /track
    if user_id != OWNER_ID:

        if not await is_group_admin(
            user_client,
            chat_id,
            user_id
        ):

            await send_message(
                chat_id,
                (
                    "❌ <b>Permission Denied</b>\n\n"
                    "Sirf Group Admin/Owner "
                    "ya Bot Owner /track use kar sakta hai."
                ),
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

    except Exception as e:

        log.warning(
            "GET GROUP ERROR | %s",
            e
        )

        title = "Unknown Group"

    add_tracked_group(
        chat_id=chat_id,
        title=title,
        added_by=user_id
    )

    log.info(
        "GROUP TRACKED | group=%s | title=%s | by=%s",
        chat_id,
        title,
        user_id
    )

    await send_message(
        chat_id,
        (
            "✅ <b>VC TRACKING ENABLED</b>\n\n"

            f"🎙️ <b>Group:</b> "
            f"{title}\n"

            f"🆔 <b>ID:</b> "
            f"<code>{chat_id}</code>\n\n"

            "👑 Owner — TRACKED\n"
            "👮 Admin — TRACKED\n"
            "👤 Members — TRACKED\n\n"

            "🟢 JOIN aur 🔴 LEAVE "
            "automatically log honge.\n\n"

            "📢 Logs configured channel me jayenge."
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
            "❌ Group ke andar use karo.",
            message_id
        )

        return

    if user_id != OWNER_ID:

        if not await is_group_admin(
            user_client,
            chat_id,
            user_id
        ):

            await send_message(
                chat_id,
                "❌ Sirf Admin/Owner use kar sakta hai.",
                message_id
            )

            return

    removed = remove_tracked_group(
        chat_id
    )

    if removed:

        text = (
            "🛑 <b>VC TRACKING DISABLED</b>\n\n"
            f"🆔 <code>{chat_id}</code>"
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
            "❌ Group ke andar use karo.",
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

    tracking_status = (
        "🟢 ACTIVE"
        if tracked
        else
        "🔴 OFF"
    )

    text = (
        "📊 <b>VC STATUS</b>\n\n"

        f"🎙️ <b>Group:</b> {title}\n"
        f"🆔 <b>ID:</b> <code>{chat_id}</code>\n\n"

        f"📡 <b>Tracking:</b> "
        f"{tracking_status}\n"

        f"👥 <b>Active VC Users:</b> "
        f"{len(active)}"
    )

    if active:

        text += "\n\n<b>Current Users:</b>\n"

        for session in active[:50]:

            name = session.get(
                "name",
                "Unknown User"
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
            "📋 <b>No tracked groups.</b>",
            message_id
        )

        return

    text = (
        "📋 <b>TRACKED GROUPS</b>\n\n"
    )

    for number, group in enumerate(
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
            f"{number}. 🎙️ <b>{title}</b>\n"
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

    sender = message.get(
        "from"
    )

    if not sender:
        return

    user_id = sender.get(
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
        "COMMAND RECEIVED | "
        "command=%s | user=%s | chat=%s",
        command,
        user_id,
        chat_id
    )

    if command == "/start":

        await command_start(
            chat_id,
            message_id
        )

    elif command == "/track":

        await command_track(
            user_client,
            chat_id,
            user_id,
            message_id
        )

    elif command == "/stoptrack":

        await command_stoptrack(
            user_client,
            chat_id,
            user_id,
            message_id
        )

    elif command == "/status":

        await command_status(
            user_client,
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
    user_client
):

    log.info(
        "BOT API POLLING STARTED"
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

                    offset = update_id + 1

                log.info(
                    "BOT UPDATE RECEIVED | %s",
                    update_id
                )

                try:

                    await handle_bot_update(
                        update,
                        user_client
                    )

                except Exception as e:

                    log.exception(
                        "COMMAND HANDLER ERROR | %s",
                        e
                    )

        except asyncio.CancelledError:

            break

        except Exception as e:

            log.exception(
                "BOT POLLING ERROR | %s",
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
        "          VC TRACKER STARTING"
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
            "❌ BOT API CONNECTION FAILED"
        )

        return

    log.info(
        "✅ BOT API CONNECTED | "
        "ID=%s | USERNAME=@%s",
        bot_info.get("id"),
        bot_info.get("username")
    )

    # --------------------------------------------------------
    # USER SESSION
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
    # IMPORTANT RAW MTProto HANDLER
    # ========================================================

    @user.on_raw_update()
    async def raw_update_handler(
        client,
        update,
        users,
        chats
    ):

        try:

            log.info(
                "🔥 RAW UPDATE RECEIVED | %s",
                type(update).__name__
            )

            # Send EVERY raw update to tracker
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

    # --------------------------------------------------------
    # START USER SESSION
    # --------------------------------------------------------

    await user.start()

    me = await user.get_me()

    log.info(
        "=========================================="
    )

    log.info(
        "✅ USER SESSION STARTED SUCCESSFULLY"
    )

    log.info(
        "USER ID       : %s",
        me.id
    )

    log.info(
        "USERNAME      : @%s",
        me.username or "none"
    )

    log.info(
        "=========================================="
    )

    # --------------------------------------------------------
    # START VC TRACKER
    # --------------------------------------------------------

    try:

        await tracker.start()

        log.info(
            "✅ VC TRACKER STARTED"
        )

    except Exception as e:

        log.exception(
            "VC TRACKER START ERROR | %s",
            e
        )

    # --------------------------------------------------------
    # STARTUP CHANNEL LOG
    # --------------------------------------------------------

    await send_log(
        (
            "🟢 <b>VC TRACKER ONLINE</b>\n\n"

            "Bot successfully started.\n\n"

            f"🤖 <b>Bot:</b> "
            f"@{bot_info.get('username')}\n"

            f"👤 <b>User Session:</b> "
            f"<code>{me.id}</code>\n\n"

            "🎙️ <b>VC Tracking:</b> READY\n"
            "📡 <b>Raw MTProto:</b> READY\n"
            "🔄 <b>VC Reconciliation:</b> READY\n"
            "🗄️ <b>MongoDB:</b> READY"
        )
    )

    # --------------------------------------------------------
    # BOT POLLING
    # --------------------------------------------------------

    polling_task = asyncio.create_task(
        bot_polling(
            user
        )
    )

    log.info(
        "✅ BOT IS READY"
    )

    log.info(
        "👀 WAITING FOR VC UPDATES..."
    )

    # --------------------------------------------------------
    # KEEP ALIVE
    # --------------------------------------------------------

    try:

        await idle()

    finally:

        log.info(
            "SHUTTING DOWN..."
        )

        # Stop polling
        polling_task.cancel()

        try:

            await polling_task

        except asyncio.CancelledError:
            pass

        # Stop tracker
        try:

            await tracker.stop()

        except Exception as e:

            log.warning(
                "TRACKER STOP ERROR | %s",
                e
            )

        # Stop user
        try:

            await user.stop()

        except Exception as e:

            log.warning(
                "USER STOP ERROR | %s",
                e
            )

        log.info(
            "VC TRACKER STOPPED"
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
            "BOT STOPPED BY USER"
        )

    except Exception as e:

        log.exception(
            "FATAL ERROR | %s",
            e
        )
import asyncio
import logging
from datetime import datetime, timezone

from pyrogram import Client, filters
from pyrogram.raw import types, functions

from config import LOG_CHANNEL, OWNER_ID
from database import (
    is_tracked,
    start_session,
    end_session,
    get_active,
    get_active_for_chat
)

log = logging.getLogger(__name__)

GROUP_CALLS = {}


def format_time(dt):
    return dt.astimezone().strftime(
        "%d-%m-%Y %I:%M:%S %p"
    )


def format_duration(seconds):
    seconds = int(seconds)

    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    parts = []

    if days:
        parts.append(f"{days}d")

    if hours:
        parts.append(f"{hours}h")

    if minutes:
        parts.append(f"{minutes}m")

    if seconds or not parts:
        parts.append(f"{seconds}s")

    return " ".join(parts)


async def send_join(bot, data):
    text = f"""
🟢 VC USER JOINED

👤 Name: {data["name"]}
🔗 Username: {data["username"]}
🆔 ID: {data["user_id"]}

🎙️ Group: {data["chat_title"]}
🕐 Joined: {format_time(data["join_time"])}
"""

    await bot.send_message(
        LOG_CHANNEL,
        text
    )


async def send_left(bot, data):
    text = f"""
🔴 VC USER LEFT

👤 Name: {data["name"]}
🔗 Username: {data["username"]}
🆔 ID: {data["user_id"]}

🎙️ Group: {data["chat_title"]}

🕐 Joined: {format_time(data["join_time"])}
🕐 Left: {format_time(data["leave_time"])}

⏱️ Duration: {format_duration(data["duration_seconds"])}
"""

    await bot.send_message(
        LOG_CHANNEL,
        text
    )


def peer_to_id(peer):
    if isinstance(peer, types.PeerUser):
        return peer.user_id

    if isinstance(peer, types.PeerChannel):
        return -1000000000000 - peer.channel_id

    if isinstance(peer, types.PeerChat):
        return -peer.chat_id

    return None


async def resolve_user(client, user_id):
    try:
        return await client.get_users(user_id)
    except Exception:
        return None


async def process_join(
    bot,
    user_client,
    chat_id,
    chat_title,
    user_id,
    join_time=None
):
    if not is_tracked(chat_id):
        return

    if get_active(user_id, chat_id):
        return

    user = await resolve_user(user_client, user_id)

    if user:
        name = user.first_name or ""

        if user.last_name:
            name += f" {user.last_name}"

        username = (
            f"@{user.username}"
            if user.username
            else "No username"
        )
    else:
        name = str(user_id)
        username = "No username"

    if join_time is None:
        join_time = datetime.now(timezone.utc)

    start_session(
        user_id=user_id,
        name=name,
        username=username,
        chat_id=chat_id,
        chat_title=chat_title,
        join_time=join_time
    )

    data = {
        "user_id": user_id,
        "name": name,
        "username": username,
        "chat_id": chat_id,
        "chat_title": chat_title,
        "join_time": join_time
    }

    await send_join(bot, data)


async def process_leave(
    bot,
    chat_id
):
    if not is_tracked(chat_id):
        return

    now = datetime.now(timezone.utc)

    active = get_active_for_chat(chat_id)

    for session in active:
        finished = end_session(
            session["user_id"],
            chat_id,
            now
        )

        if finished:
            await send_left(
                bot,
                finished
            )


async def handle_participants(
    bot,
    user_client,
    chat_id,
    participants
):
    if not is_tracked(chat_id):
        return

    current_ids = set()

    for participant in participants:

        user_id = peer_to_id(
            participant.peer
        )

        if not user_id:
            continue

        if getattr(participant, "left", False):
            continue

        current_ids.add(user_id)

        join_timestamp = getattr(
            participant,
            "date",
            None
        )

        join_time = None

        if join_timestamp:
            try:
                join_time = datetime.fromtimestamp(
                    join_timestamp,
                    tz=timezone.utc
                )
            except Exception:
                pass

        if not get_active(user_id, chat_id):

            await process_join(
                bot,
                user_client,
                chat_id,
                GROUP_CALLS.get(
                    chat_id,
                    {}
                ).get(
                    "title",
                    "Unknown Group"
                ),
                user_id,
                join_time
            )

    active = get_active_for_chat(chat_id)

    for session in active:

        if session["user_id"] not in current_ids:

            finished = end_session(
                session["user_id"],
                chat_id,
                datetime.now(timezone.utc)
            )

            if finished:
                await send_left(
                    bot,
                    finished
                )


@Client.on_raw_update()
async def raw_update(
    user_client,
    update,
    users,
    chats
):
    try:

        log.info(
            "RAW UPDATE: %s",
            type(update).__name__
        )

        if isinstance(
            update,
            types.UpdateGroupCall
        ):

            call = update.call

            if isinstance(
                call,
                types.GroupCall
            ):

                chat_id = (
                    -1000000000000
                    - update.chat_id
                )

                GROUP_CALLS.setdefault(
                    chat_id,
                    {}
                )

                GROUP_CALLS[chat_id][
                    "call_id"
                ] = call.id

                GROUP_CALLS[chat_id][
                    "access_hash"
                ] = call.access_hash

                try:
                    chat = await user_client.get_chat(
                        chat_id
                    )

                    GROUP_CALLS[chat_id][
                        "title"
                    ] = chat.title

                except Exception:
                    GROUP_CALLS[chat_id][
                        "title"
                    ] = "Unknown Group"

        elif isinstance(
            update,
            types.UpdateGroupCallParticipants
        ):

            call = update.call

            for chat_id, info in list(
                GROUP_CALLS.items()
            ):

                if (
                    info.get("call_id")
                    == call.id
                ):

                    await handle_participants(
                        None,
                        user_client,
                        chat_id,
                        update.participants
                    )

    except Exception:
        log.exception(
            "Raw update error"
        )
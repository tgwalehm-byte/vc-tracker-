import asyncio
import logging
from datetime import datetime, timezone

from pyrogram import Client
from pyrogram.raw import types

from database import (
    is_tracked,
    start_session,
    get_active,
    get_active_for_chat,
    end_session,
)

log = logging.getLogger(__name__)

IST_FORMAT = "%d-%m-%Y %I:%M:%S %p"


def format_time(dt):
    return dt.astimezone().strftime(IST_FORMAT)


def format_duration(seconds):
    seconds = int(seconds)

    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    result = []

    if days:
        result.append(f"{days}d")

    if hours:
        result.append(f"{hours}h")

    if minutes:
        result.append(f"{minutes}m")

    if seconds or not result:
        result.append(f"{seconds}s")

    return " ".join(result)


def peer_to_id(peer):
    if isinstance(peer, types.PeerUser):
        return peer.user_id

    if isinstance(peer, types.PeerChannel):
        return -1000000000000 - peer.channel_id

    if isinstance(peer, types.PeerChat):
        return -peer.chat_id

    return None


class VCTracker:

    def __init__(self, bot, user):
        self.bot = bot
        self.user = user

        # call_id -> chat_id
        self.call_to_chat = {}

        # chat_id -> title
        self.chat_titles = {}

        self.running = True

        # Raw update handler
        self.user.add_handler(
            __import__(
                "pyrogram.handlers",
                fromlist=["RawUpdateHandler"]
            ).RawUpdateHandler(
                self.raw_update
            )
        )

    async def send_join(
        self,
        user_id,
        name,
        username,
        chat_id,
        chat_title,
        join_time
    ):
        text = (
            "🟢 VC USER JOINED\n\n"
            f"👤 Name: {name}\n"
            f"🔗 Username: {username}\n"
            f"🆔 ID: {user_id}\n\n"
            f"🎙️ Group: {chat_title}\n"
            f"🕐 Joined: {format_time(join_time)}"
        )

        try:
            await self.bot.send_message(
                LOG_CHANNEL,
                text
            )
        except Exception:
            log.exception("Failed to send JOIN log")

    async def send_left(self, data):

        text = (
            "🔴 VC USER LEFT\n\n"
            f"👤 Name: {data['name']}\n"
            f"🔗 Username: {data.get('username') or 'No username'}\n"
            f"🆔 ID: {data['user_id']}\n\n"
            f"🎙️ Group: {data['chat_title']}\n\n"
            f"🕐 Joined: {format_time(data['join_time'])}\n"
            f"🕐 Left: {format_time(data['leave_time'])}\n\n"
            f"⏱️ Duration: {format_duration(data['duration_seconds'])}"
        )

        try:
            await self.bot.send_message(
                LOG_CHANNEL,
                text
            )
        except Exception:
            log.exception("Failed to send LEFT log")

    async def get_user(self, user_id):

        try:
            return await self.user.get_users(user_id)
        except Exception:
            return None

    async def process_join(
        self,
        chat_id,
        user_id,
        join_time=None
    ):

        if not is_tracked(chat_id):
            return

        # Already active
        if get_active(user_id, chat_id):
            return

        user = await self.get_user(user_id)

        if user:

            name = user.first_name or "Unknown"

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

        chat_title = self.chat_titles.get(
            chat_id,
            "Unknown Group"
        )

        start_session(
            user_id=user_id,
            name=name,
            username=username,
            chat_id=chat_id,
            chat_title=chat_title,
            join_time=join_time
        )

        await self.send_join(
            user_id=user_id,
            name=name,
            username=username,
            chat_id=chat_id,
            chat_title=chat_title,
            join_time=join_time
        )

        log.info(
            "JOIN | %s | %s",
            user_id,
            chat_id
        )

    async def process_leave(
        self,
        chat_id,
        user_id
    ):

        if not is_tracked(chat_id):
            return

        if not get_active(user_id, chat_id):
            return

        leave_time = datetime.now(timezone.utc)

        finished = end_session(
            user_id,
            chat_id,
            leave_time
        )

        if finished:
            await self.send_left(finished)

            log.info(
                "LEFT | %s | %s | %ss",
                user_id,
                chat_id,
                finished["duration_seconds"]
            )

    async def handle_participants(
        self,
        chat_id,
        participants
    ):

        if not is_tracked(chat_id):
            return

        current_users = set()

        for participant in participants:

            user_id = peer_to_id(
                participant.peer
            )

            if not user_id:
                continue

            is_left = getattr(
                participant,
                "left",
                False
            )

            if is_left:
                await self.process_leave(
                    chat_id,
                    user_id
                )
                continue

            current_users.add(user_id)

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
                    join_time = None

            if not get_active(
                user_id,
                chat_id
            ):
                await self.process_join(
                    chat_id,
                    user_id,
                    join_time
                )

        # Important:
        # Participant update me jo active users nahi aaye,
        # unko leave maana jayega.
        active = get_active_for_chat(
            chat_id
        )

        for session in active:

            uid = session["user_id"]

            if uid not in current_users:

                await self.process_leave(
                    chat_id,
                    uid
                )

    async def raw_update(
        self,
        client,
        update,
        users,
        chats
    ):

        try:

            log.info(
                "RAW UPDATE RECEIVED: %s",
                type(update).__name__
            )

            # --------------------------------
            # VC UPDATE
            # --------------------------------

            if isinstance(
                update,
                types.UpdateGroupCall
            ):

                call = update.call

                chat_id = (
                    -1000000000000
                    - update.chat_id
                )

                try:
                    chat = await self.user.get_chat(
                        chat_id
                    )

                    title = (
                        chat.title
                        or "Unknown Group"
                    )

                except Exception:

                    title = "Unknown Group"

                self.chat_titles[
                    chat_id
                ] = title

                # Active call
                if isinstance(
                    call,
                    types.GroupCall
                ):

                    self.call_to_chat[
                        call.id
                    ] = chat_id

                    log.info(
                        "VC FOUND | chat=%s | call=%s",
                        chat_id,
                        call.id
                    )

                # VC ended
                elif isinstance(
                    call,
                    types.GroupCallDiscarded
                ):

                    self.call_to_chat.pop(
                        call.id,
                        None
                    )

                    log.info(
                        "VC ENDED | chat=%s",
                        chat_id
                    )

            # --------------------------------
            # PARTICIPANTS UPDATE
            # --------------------------------

            elif isinstance(
                update,
                types.UpdateGroupCallParticipants
            ):

                call = update.call

                chat_id = self.call_to_chat.get(
                    call.id
                )

                if not chat_id:

                    log.warning(
                        "Participant update received "
                        "but call_id not mapped: %s",
                        call.id
                    )

                    return

                log.info(
                    "PARTICIPANTS UPDATE | chat=%s | count=%s",
                    chat_id,
                    len(update.participants)
                )

                await self.handle_participants(
                    chat_id,
                    update.participants
                )

        except Exception:

            log.exception(
                "RAW UPDATE ERROR"
            )

    async def stop(self):

        self.running = False
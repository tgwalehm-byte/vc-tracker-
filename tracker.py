import logging
from datetime import datetime, timezone

from pyrogram import Client
from pyrogram.raw import types

from database import (
    start_session,
    get_active,
    end_session
)

logger = logging.getLogger(__name__)


def utc_now():
    return datetime.now(timezone.utc)


def format_time(dt):
    return dt.astimezone().strftime(
        "%d-%m-%Y %I:%M:%S %p"
    )


def format_duration(seconds):
    seconds = max(0, int(seconds))

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


def user_name(user):
    name = "Unknown User"

    if user:
        name = (
            f"{user.first_name or ''} "
            f"{user.last_name or ''}"
        ).strip()

    return name or "Unknown User"


def username_text(username):
    return f"@{username}" if username else "No username"


class VCTracker:

    def __init__(self, client: Client, logger_func):
        self.client = client
        self.logger_func = logger_func

        # call_id -> chat_id
        self.call_map = {}

        # chat_id -> title
        self.chat_titles = {}

    async def register_call(self, chat_id, call):

        call_id = getattr(call, "id", None)

        if not call_id:
            return

        self.call_map[call_id] = chat_id

        if chat_id not in self.chat_titles:

            try:
                chat = await self.client.get_chat(chat_id)

                self.chat_titles[chat_id] = (
                    chat.title or "Voice Chat"
                )

            except Exception:

                self.chat_titles[chat_id] = "Voice Chat"

    async def process_participant(
        self,
        call,
        participant,
        users
    ):

        call_id = getattr(call, "id", None)

        if not call_id:
            return

        chat_id = self.call_map.get(call_id)

        if not chat_id:
            return

        peer = getattr(participant, "peer", None)

        if not isinstance(peer, types.PeerUser):
            return

        user_id = peer.user_id

        user = users.get(user_id)

        if not user:

            try:
                user = await self.client.get_users(
                    user_id
                )
            except Exception:
                user = None

        name = user_name(user)

        username = (
            getattr(user, "username", None)
            if user else None
        )

        title = self.chat_titles.get(
            chat_id,
            "Voice Chat"
        )

        left = getattr(
            participant,
            "left",
            False
        )

        just_joined = getattr(
            participant,
            "just_joined",
            False
        )

        # -------------------------
        # USER LEFT
        # -------------------------

        if left:

            active = get_active(
                user_id,
                chat_id
            )

            if not active:
                return

            leave_time = utc_now()

            finished = end_session(
                user_id,
                chat_id,
                leave_time
            )

            if not finished:
                return

            text = (
                "🔴 <b>VC USER LEFT</b>\n\n"
                f"👤 <b>Name:</b> {name}\n"
                f"🔗 <b>Username:</b> "
                f"{username_text(username)}\n"
                f"🆔 <b>ID:</b> "
                f"<code>{user_id}</code>\n\n"
                f"🎙️ <b>Group:</b> {title}\n\n"
                f"🟢 <b>Joined:</b> "
                f"{format_time(finished['join_time'])}\n"
                f"🔴 <b>Left:</b> "
                f"{format_time(finished['leave_time'])}\n"
                f"⏱️ <b>Stayed:</b> "
                f"{format_duration(finished['duration_seconds'])}"
            )

            await self.logger_func(text)

            return

        # -------------------------
        # USER JOINED
        # -------------------------

        if not just_joined:
            return

        if get_active(
            user_id,
            chat_id
        ):
            return

        join_time = utc_now()

        start_session(
            user_id,
            name,
            username,
            chat_id,
            title,
            join_time
        )

        text = (
            "🟢 <b>VC USER JOINED</b>\n\n"
            f"👤 <b>Name:</b> {name}\n"
            f"🔗 <b>Username:</b> "
            f"{username_text(username)}\n"
            f"🆔 <b>ID:</b> "
            f"<code>{user_id}</code>\n\n"
            f"🎙️ <b>Group:</b> {title}\n"
            f"🕐 <b>Joined:</b> "
            f"{format_time(join_time)}"
        )

        await self.logger_func(text)

    def call_ended(self, call):

        call_id = getattr(call, "id", None)

        if call_id:
            self.call_map.pop(
                call_id,
                None
            )
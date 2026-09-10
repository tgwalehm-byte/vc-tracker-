import logging
import html
from datetime import datetime, timezone

from pyrogram import Client
from pyrogram.raw import types

from database import (
    start_session,
    get_active,
    end_session,
    is_tracked
)

log = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc)


def telegram_time(timestamp):
    if not timestamp:
        return now()

    return datetime.fromtimestamp(
        int(timestamp),
        tz=timezone.utc
    )


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


def get_name(user):
    if not user:
        return "Unknown User"

    first = getattr(user, "first_name", None) or ""
    last = getattr(user, "last_name", None) or ""

    name = f"{first} {last}".strip()

    return name or "Unknown User"


class VCTracker:

    def __init__(self, client: Client, log_func):
        self.client = client
        self.log_func = log_func

        # call_id -> telegram chat_id
        self.calls = {}

        # chat_id -> title
        self.titles = {}

    async def register_call(self, chat_id, call):

        if not is_tracked(chat_id):
            log.info(
                "VC UPDATE IGNORED | group=%s | not tracked",
                chat_id
            )
            return

        call_id = getattr(call, "id", None)

        if not call_id:
            return

        self.calls[call_id] = chat_id

        if chat_id not in self.titles:

            try:
                chat = await self.client.get_chat(chat_id)

                self.titles[chat_id] = (
                    chat.title or "Voice Chat"
                )

            except Exception as e:

                log.exception(
                    "Could not get group title: %s",
                    e
                )

                self.titles[chat_id] = "Voice Chat"

        log.info(
            "VC REGISTERED | group=%s | call=%s | title=%s",
            chat_id,
            call_id,
            self.titles.get(chat_id)
        )

    async def participant(
        self,
        call,
        participant,
        users
    ):

        call_id = getattr(call, "id", None)

        if not call_id:
            return

        chat_id = self.calls.get(call_id)

        if not chat_id:
            log.warning(
                "PARTICIPANT UPDATE BUT CALL UNKNOWN | call=%s",
                call_id
            )
            return

        if not is_tracked(chat_id):
            return

        peer = getattr(
            participant,
            "peer",
            None
        )

        if not isinstance(
            peer,
            types.PeerUser
        ):
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

        name = get_name(user)

        username = (
            getattr(
                user,
                "username",
                None
            )
            if user
            else None
        )

        safe_name = html.escape(name)

        username_text = (
            f"@{html.escape(username)}"
            if username
            else "No username"
        )

        title = self.titles.get(
            chat_id,
            "Voice Chat"
        )

        safe_title = html.escape(title)

        # ==========================
        # USER LEFT
        # ==========================

        if getattr(
            participant,
            "left",
            False
        ):

            active = get_active(
                user_id,
                chat_id
            )

            if not active:
                log.info(
                    "VC LEAVE IGNORED | no active session | user=%s | group=%s",
                    user_id,
                    chat_id
                )
                return

            finished = end_session(
                user_id,
                chat_id,
                now()
            )

            if not finished:
                return

            text = (
                "🔴 <b>VC USER LEFT</b>\n\n"

                f"👤 <b>Name:</b> {safe_name}\n"
                f"🔗 <b>Username:</b> {username_text}\n"
                f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"

                f"🎙️ <b>Group:</b> {safe_title}\n\n"

                f"🟢 <b>Joined:</b> "
                f"{format_time(finished['join_time'])}\n"

                f"🔴 <b>Left:</b> "
                f"{format_time(finished['leave_time'])}\n"

                f"⏱️ <b>Stayed:</b> "
                f"{format_duration(finished['duration_seconds'])}"
            )

            try:
                await self.log_func(text)

                log.info(
                    "VC LEAVE LOG SENT | user=%s | group=%s",
                    user_id,
                    chat_id
                )

            except Exception as e:

                log.exception(
                    "FAILED TO SEND LEAVE LOG: %s",
                    e
                )

            return

        # ==========================
        # USER JOINED
        # ==========================

        if not getattr(
            participant,
            "just_joined",
            False
        ):
            return

        if get_active(
            user_id,
            chat_id
        ):
            return

        participant_date = getattr(
            participant,
            "date",
            None
        )

        join_time = telegram_time(
            participant_date
        )

        start_session(
            user_id=user_id,
            name=name,
            username=username,
            chat_id=chat_id,
            chat_title=title,
            join_time=join_time
        )

        text = (
            "🟢 <b>VC USER JOINED</b>\n\n"

            f"👤 <b>Name:</b> {safe_name}\n"
            f"🔗 <b>Username:</b> {username_text}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"

            f"🎙️ <b>Group:</b> {safe_title}\n"

            f"🕐 <b>Joined:</b> "
            f"{format_time(join_time)}"
        )

        try:

            await self.log_func(text)

            log.info(
                "VC JOIN LOG SENT | user=%s | group=%s | join=%s",
                user_id,
                chat_id,
                join_time
            )

        except Exception as e:

            log.exception(
                "FAILED TO SEND JOIN LOG: %s",
                e
            )

    async def raw_update(
        self,
        update,
        users,
        chats
    ):

        # ==========================
        # NEW / UPDATED VC
        # ==========================

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
                return

            # MTProto channel ID -> Bot API chat ID
            chat_id = (
                -1000000000000
                - int(raw_chat_id)
            )

            log.info(
                "RAW VC UPDATE | raw_chat=%s | chat=%s",
                raw_chat_id,
                chat_id
            )

            await self.register_call(
                chat_id,
                call
            )

            return

        # ==========================
        # VC PARTICIPANTS
        # ==========================

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
                "RAW VC PARTICIPANTS | call=%s | participants=%s",
                call_id,
                len(participants)
            )

            if call_id and call_id not in self.calls:

                log.warning(
                    "CALL NOT REGISTERED YET | call=%s",
                    call_id
                )

                return

            for participant in participants:

                try:

                    await self.participant(
                        call,
                        participant,
                        users
                    )

                except Exception as e:

                    log.exception(
                        "PARTICIPANT PROCESSING ERROR: %s",
                        e
                    )

            return
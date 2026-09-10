import logging
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


# ==========================================
# TIME
# ==========================================

def now():

    return datetime.now(
        timezone.utc
    )


def telegram_time(timestamp):

    if not timestamp:
        return now()

    return datetime.fromtimestamp(
        int(timestamp),
        tz=timezone.utc
    )


# ==========================================
# FORMAT
# ==========================================

def format_time(dt):

    return dt.astimezone().strftime(
        "%d-%m-%Y %I:%M:%S %p"
    )


def format_duration(seconds):

    seconds = max(
        0,
        int(seconds)
    )

    days, seconds = divmod(
        seconds,
        86400
    )

    hours, seconds = divmod(
        seconds,
        3600
    )

    minutes, seconds = divmod(
        seconds,
        60
    )

    parts = []

    if days:
        parts.append(
            f"{days}d"
        )

    if hours:
        parts.append(
            f"{hours}h"
        )

    if minutes:
        parts.append(
            f"{minutes}m"
        )

    if seconds or not parts:
        parts.append(
            f"{seconds}s"
        )

    return " ".join(parts)


# ==========================================
# NAME
# ==========================================

def get_name(user):

    if not user:
        return "Unknown User"

    first = (
        getattr(
            user,
            "first_name",
            None
        )
        or ""
    )

    last = (
        getattr(
            user,
            "last_name",
            None
        )
        or ""
    )

    name = (
        f"{first} {last}"
    ).strip()

    return name or "Unknown User"


# ==========================================
# TRACKER
# ==========================================

class VCTracker:

    def __init__(
        self,
        client: Client,
        log_func
    ):

        self.client = client

        self.log_func = log_func

        # call_id -> chat_id
        self.calls = {}

        # chat_id -> title
        self.titles = {}


    # ======================================
    # REGISTER CALL
    # ======================================

    async def register_call(
        self,
        chat_id,
        call
    ):

        if not is_tracked(chat_id):
            return


        call_id = getattr(
            call,
            "id",
            None
        )

        if not call_id:
            return


        self.calls[call_id] = chat_id


        if chat_id not in self.titles:

            try:

                chat = await self.client.get_chat(
                    chat_id
                )

                self.titles[chat_id] = (
                    chat.title
                    or "Voice Chat"
                )

            except Exception:

                self.titles[chat_id] = (
                    "Voice Chat"
                )


        log.info(
            "VC REGISTERED | group=%s | call=%s",
            chat_id,
            call_id
        )


    # ======================================
    # PARTICIPANT
    # ======================================

    async def participant(
        self,
        call,
        participant,
        users
    ):

        call_id = getattr(
            call,
            "id",
            None
        )

        if not call_id:
            return


        chat_id = self.calls.get(
            call_id
        )

        if not chat_id:
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


        user = users.get(
            user_id
        )


        if not user:

            try:

                user = await self.client.get_users(
                    user_id
                )

            except Exception:

                user = None


        name = get_name(
            user
        )


        username = (
            getattr(
                user,
                "username",
                None
            )
            if user
            else None
        )


        username_text = (
            f"@{username}"
            if username
            else "No username"
        )


        title = self.titles.get(
            chat_id,
            "Voice Chat"
        )


        # ==================================
        # LEAVE
        # ==================================

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

                f"👤 <b>Name:</b> "
                f"{name}\n"

                f"🔗 <b>Username:</b> "
                f"{username_text}\n"

                f"🆔 <b>ID:</b> "
                f"<code>{user_id}</code>\n\n"

                f"🎙️ <b>Group:</b> "
                f"{title}\n\n"

                f"🟢 <b>Joined:</b> "
                f"{format_time(finished['join_time'])}\n"

                f"🔴 <b>Left:</b> "
                f"{format_time(finished['leave_time'])}\n"

                f"⏱️ <b>Stayed:</b> "
                f"{format_duration(finished['duration_seconds'])}"
            )


            await self.log_func(
                text
            )


            log.info(
                "VC LEAVE | user=%s | group=%s",
                user_id,
                chat_id
            )

            return


        # ==================================
        # JOIN
        # ==================================

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

            f"👤 <b>Name:</b> "
            f"{name}\n"

            f"🔗 <b>Username:</b> "
            f"{username_text}\n"

            f"🆔 <b>ID:</b> "
            f"<code>{user_id}</code>\n\n"

            f"🎙️ <b>Group:</b> "
            f"{title}\n"

            f"🕐 <b>Joined:</b> "
            f"{format_time(join_time)}"
        )


        await self.log_func(
            text
        )


        log.info(
            "VC JOIN | user=%s | group=%s",
            user_id,
            chat_id
        )


    # ======================================
    # CALL END
    # ======================================

    def end_call(self, call):

        call_id = getattr(
            call,
            "id",
            None
        )

        if call_id:

            self.calls.pop(
                call_id,
                None
            )
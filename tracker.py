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


# =====================================
# TIME
# =====================================

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


# =====================================
# FORMAT TIME
# =====================================

def format_time(dt):

    return dt.astimezone().strftime(
        "%d-%m-%Y %I:%M:%S %p"
    )


# =====================================
# FORMAT DURATION
# =====================================

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

    result = []

    if days:
        result.append(
            f"{days}d"
        )

    if hours:
        result.append(
            f"{hours}h"
        )

    if minutes:
        result.append(
            f"{minutes}m"
        )

    if seconds or not result:
        result.append(
            f"{seconds}s"
        )

    return " ".join(result)


# =====================================
# USER NAME
# =====================================

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


# =====================================
# VC TRACKER
# =====================================

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


    # =================================
    # REGISTER CALL
    # =================================

    async def register_call(
        self,
        chat_id,
        call
    ):

        call_id = getattr(
            call,
            "id",
            None
        )

        if not call_id:
            return


        # Only selected groups
        if not is_tracked(chat_id):
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
            "VC REGISTERED | Group=%s | Call=%s",
            chat_id,
            call_id
        )


    # =================================
    # PARTICIPANT
    # =================================

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


        # Safety check
        if not is_tracked(chat_id):
            return


        peer = getattr(
            participant,
            "peer",
            None
        )


        # We only track normal users
        if not isinstance(
            peer,
            types.PeerUser
        ):
            return


        user_id = peer.user_id


        # =================================
        # GET USER
        # =================================

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


        # =================================
        # USER LEFT
        # =================================

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


            leave_time = now()


            finished = end_session(
                user_id,
                chat_id,
                leave_time
            )


            if not finished:
                return


            log.info(
                "VC LEAVE | User=%s | Group=%s",
                user_id,
                chat_id
            )


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

            return


        # =================================
        # ONLY NEW JOIN
        # =================================

        if not getattr(
            participant,
            "just_joined",
            False
        ):
            return


        # Already active
        if get_active(
            user_id,
            chat_id
        ):

            return


        # =================================
        # EXACT TELEGRAM JOIN TIME
        # =================================

        participant_date = getattr(
            participant,
            "date",
            None
        )


        if participant_date:

            join_time = telegram_time(
                participant_date
            )

        else:

            join_time = now()


        # =================================
        # SAVE
        # =================================

        start_session(
            user_id=user_id,
            name=name,
            username=username,
            chat_id=chat_id,
            chat_title=title,
            join_time=join_time
        )


        log.info(
            "VC JOIN | User=%s | Group=%s",
            user_id,
            chat_id
        )


        # =================================
        # LOG
        # =================================

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


    # =================================
    # CALL ENDED
    # =================================

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

            log.info(
                "VC CALL ENDED | Call=%s",
                call_id
            )
import asyncio
import html
import logging
from datetime import datetime, timezone

from pyrogram import Client
from pyrogram.raw import functions, types

from database import (
    start_session,
    get_active,
    end_session,
    is_tracked,
    get_active_for_chat
)

log = logging.getLogger("VC-TRACKER")


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


def peer_user_id(peer):
    if isinstance(peer, types.PeerUser):
        return peer.user_id

    return None


class VCTracker:

    def __init__(self, client: Client, log_func):
        self.client = client
        self.log_func = log_func

        # call_id -> chat_id
        self.calls = {}

        # chat_id -> title
        self.titles = {}

        # chat_id -> last known participant IDs
        self.last_participants = {}

        # Prevent multiple reconciliation jobs
        self.reconcile_tasks = {}

    # ========================================================
    # REGISTER VC
    # ========================================================

    async def register_call(self, chat_id, call):

        if not is_tracked(chat_id):
            log.info(
                "VC IGNORED | group=%s | not tracked",
                chat_id
            )
            return

        call_id = getattr(call, "id", None)

        if not call_id:
            log.warning(
                "VC has no call ID | group=%s",
                chat_id
            )
            return

        self.calls[call_id] = chat_id

        if chat_id not in self.titles:

            try:
                chat = await self.client.get_chat(
                    chat_id
                )

                self.titles[chat_id] = (
                    getattr(chat, "title", None)
                    or "Voice Chat"
                )

            except Exception as e:

                log.warning(
                    "GROUP TITLE ERROR | %s",
                    e
                )

                self.titles[chat_id] = "Voice Chat"

        log.info(
            "VC REGISTERED | group=%s | call=%s | title=%s",
            chat_id,
            call_id,
            self.titles[chat_id]
        )

        # Immediately reconcile current VC users
        await self.reconcile_call(
            chat_id,
            call
        )

    # ========================================================
    # USER INFORMATION
    # ========================================================

    async def get_user_info(
        self,
        user_id,
        users=None
    ):

        user = None

        if users:
            user = users.get(user_id)

        if not user:

            try:
                user = await self.client.get_users(
                    user_id
                )

            except Exception:
                user = None

        return user

    # ========================================================
    # SEND JOIN LOG
    # ========================================================

    async def send_join(
        self,
        chat_id,
        user_id,
        user,
        join_time=None
    ):

        if join_time is None:
            join_time = now()

        name = get_name(user)

        username = (
            getattr(user, "username", None)
            if user
            else None
        )

        safe_name = html.escape(name)

        username_text = (
            f"@{html.escape(username)}"
            if username
            else "No username"
        )

        title = html.escape(
            self.titles.get(
                chat_id,
                "Voice Chat"
            )
        )

        start_session(
            user_id=user_id,
            name=name,
            username=username,
            chat_id=chat_id,
            chat_title=self.titles.get(
                chat_id,
                "Voice Chat"
            ),
            join_time=join_time
        )

        text = (
            "🟢 <b>VC USER JOINED</b>\n\n"

            f"👤 <b>Name:</b> {safe_name}\n"
            f"🔗 <b>Username:</b> {username_text}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"

            f"🎙️ <b>Group:</b> {title}\n"
            f"🕐 <b>Joined:</b> "
            f"{format_time(join_time)}"
        )

        try:

            await self.log_func(text)

            log.info(
                "JOIN LOG SENT | user=%s | group=%s",
                user_id,
                chat_id
            )

        except Exception as e:

            log.exception(
                "JOIN LOG ERROR | %s",
                e
            )

    # ========================================================
    # SEND LEAVE LOG
    # ========================================================

    async def send_leave(
        self,
        chat_id,
        user_id,
        user=None
    ):

        active = get_active(
            user_id,
            chat_id
        )

        if not active:

            log.info(
                "LEAVE IGNORED | no active session | "
                "user=%s | group=%s",
                user_id,
                chat_id
            )

            return

        leave_time = now()

        finished = end_session(
            user_id,
            chat_id,
            leave_time
        )

        if not finished:
            return

        name = (
            get_name(user)
            if user
            else finished.get(
                "name",
                "Unknown User"
            )
        )

        username = (
            getattr(user, "username", None)
            if user
            else finished.get("username")
        )

        safe_name = html.escape(name)

        username_text = (
            f"@{html.escape(username)}"
            if username
            else "No username"
        )

        title = html.escape(
            finished.get(
                "chat_title",
                self.titles.get(
                    chat_id,
                    "Voice Chat"
                )
            )
        )

        text = (
            "🔴 <b>VC USER LEFT</b>\n\n"

            f"👤 <b>Name:</b> {safe_name}\n"
            f"🔗 <b>Username:</b> {username_text}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"

            f"🎙️ <b>Group:</b> {title}\n\n"

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
                "LEAVE LOG SENT | user=%s | group=%s",
                user_id,
                chat_id
            )

        except Exception as e:

            log.exception(
                "LEAVE LOG ERROR | %s",
                e
            )

    # ========================================================
    # PROCESS ONE PARTICIPANT UPDATE
    # ========================================================

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
            log.warning(
                "UNKNOWN CALL | call=%s",
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

        user_id = peer_user_id(
            peer
        )

        if not user_id:
            return

        user = await self.get_user_info(
            user_id,
            users
        )

        # -----------------------------
        # LEAVE
        # -----------------------------

        if getattr(
            participant,
            "left",
            False
        ):

            await self.send_leave(
                chat_id,
                user_id,
                user
            )

            return

        # -----------------------------
        # JOIN
        # -----------------------------

        if getattr(
            participant,
            "just_joined",
            False
        ):

            if get_active(
                user_id,
                chat_id
            ):

                return

            join_time = telegram_time(
                getattr(
                    participant,
                    "date",
                    None
                )
            )

            await self.send_join(
                chat_id,
                user_id,
                user,
                join_time
            )

    # ========================================================
    # PARTICIPANT BATCH
    # ========================================================

    async def participant_batch(
        self,
        call,
        participants,
        users
    ):

        for participant in participants:

            try:

                await self.participant(
                    call,
                    participant,
                    users
                )

            except Exception as e:

                log.exception(
                    "PARTICIPANT ERROR | %s",
                    e
                )

    # ========================================================
    # GET CURRENT VC PARTICIPANTS
    # ========================================================

    async def get_current_participants(
        self,
        call
    ):

        call_id = getattr(
            call,
            "id",
            None
        )

        access_hash = getattr(
            call,
            "access_hash",
            None
        )

        if not call_id or not access_hash:
            log.warning(
                "Cannot fetch participants | "
                "call=%s | access_hash=%s",
                call_id,
                access_hash
            )
            return []

        try:

            result = await self.client.invoke(
                functions.phone.GetGroupParticipants(
                    call=types.InputGroupCall(
                        id=call_id,
                        access_hash=access_hash
                    ),
                    ids=[],
                    sources=[],
                    offset="",
                    limit=100
                )
            )

            participants = getattr(
                result,
                "participants",
                []
            )

            log.info(
                "VC PARTICIPANTS FETCHED | "
                "call=%s | count=%s",
                call_id,
                len(participants)
            )

            return participants

        except Exception as e:

            log.exception(
                "GET PARTICIPANTS ERROR | call=%s | %s",
                call_id,
                e
            )

            return []

    # ========================================================
    # RECONCILE VC
    # ========================================================

    async def reconcile_call(
        self,
        chat_id,
        call
    ):

        if not is_tracked(chat_id):
            return

        participants = await self.get_current_participants(
            call
        )

        if participants is None:
            return

        current_ids = set()

        # ---------------------------------
        # Build current participant list
        # ---------------------------------

        for participant in participants:

            peer = getattr(
                participant,
                "peer",
                None
            )

            user_id = peer_user_id(
                peer
            )

            if user_id:
                current_ids.add(
                    user_id
                )

        previous_ids = self.last_participants.get(
            chat_id,
            set()
        )

        # ---------------------------------
        # First successful reconciliation
        # ---------------------------------

        if chat_id not in self.last_participants:

            log.info(
                "INITIAL VC RECONCILIATION | "
                "group=%s | users=%s",
                chat_id,
                len(current_ids)
            )

            for participant in participants:

                peer = getattr(
                    participant,
                    "peer",
                    None
                )

                user_id = peer_user_id(
                    peer
                )

                if not user_id:
                    continue

                if get_active(
                    user_id,
                    chat_id
                ):
                    continue

                user = await self.get_user_info(
                    user_id
                )

                participant_date = getattr(
                    participant,
                    "date",
                    None
                )

                join_time = telegram_time(
                    participant_date
                )

                await self.send_join(
                    chat_id,
                    user_id,
                    user,
                    join_time
                )

            self.last_participants[
                chat_id
            ] = current_ids

            return

        # ---------------------------------
        # New users
        # ---------------------------------

        joined_ids = (
            current_ids - previous_ids
        )

        # ---------------------------------
        # Left users
        # ---------------------------------

        left_ids = (
            previous_ids - current_ids
        )

        if joined_ids:

            log.info(
                "RECONCILE JOIN | group=%s | users=%s",
                chat_id,
                list(joined_ids)
            )

        if left_ids:

            log.info(
                "RECONCILE LEAVE | group=%s | users=%s",
                chat_id,
                list(left_ids)
            )

        for user_id in joined_ids:

            if get_active(
                user_id,
                chat_id
            ):
                continue

            user = await self.get_user_info(
                user_id
            )

            await self.send_join(
                chat_id,
                user_id,
                user,
                now()
            )

        for user_id in left_ids:

            user = await self.get_user_info(
                user_id
            )

            await self.send_leave(
                chat_id,
                user_id,
                user
            )

        self.last_participants[
            chat_id
        ] = current_ids

    # ========================================================
    # START RECONCILIATION LOOP
    # ========================================================

    async def start_reconciliation(
        self,
        chat_id,
        call,
        seconds=3
    ):

        if chat_id in self.reconcile_tasks:
            return

        async def loop():

            log.info(
                "RECONCILIATION STARTED | group=%s | every=%ss",
                chat_id,
                seconds
            )

            while is_tracked(chat_id):

                try:

                    await self.reconcile_call(
                        chat_id,
                        call
                    )

                except Exception as e:

                    log.exception(
                        "RECONCILIATION ERROR | %s",
                        e
                    )

                await asyncio.sleep(
                    seconds
                )

            log.info(
                "RECONCILIATION STOPPED | group=%s",
                chat_id
            )

        task = asyncio.create_task(
            loop()
        )

        self.reconcile_tasks[
            chat_id
        ] = task

    # ========================================================
    # RAW UPDATE
    # ========================================================

    async def raw_update(
        self,
        update,
        users,
        chats
    ):

        # ---------------------------------
        # VC update
        # ---------------------------------

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

            await self.register_call(
                chat_id,
                call
            )

            await self.start_reconciliation(
                chat_id,
                call
            )

            return

        # ---------------------------------
        # Participant update
        # ---------------------------------

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
                "call=%s | count=%s",
                call_id,
                len(participants)
            )

            if call_id not in self.calls:

                log.warning(
                    "CALL UNKNOWN, REGISTERING FROM PARTICIPANT UPDATE | "
                    "call=%s",
                    call_id
                )

                return

            await self.participant_batch(
                call,
                participants,
                users
            )

            return
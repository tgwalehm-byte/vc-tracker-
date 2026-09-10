import asyncio
import html
import logging
import time
from datetime import datetime, timezone

from pyrogram import Client
from pyrogram.raw import functions, types
from pyrogram.errors import FloodWait

from database import (
    start_session,
    get_active,
    end_session,
    is_tracked,
    get_active_for_chat,
)

log = logging.getLogger("VC-TRACKER")


# ============================================================
# TIME
# ============================================================

def now():
    return datetime.now(timezone.utc)


def telegram_time(timestamp):
    if not timestamp:
        return now()

    try:
        return datetime.fromtimestamp(
            int(timestamp),
            tz=timezone.utc
        )
    except Exception:
        return now()


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


def get_user_id(participant):
    peer = getattr(
        participant,
        "peer",
        None
    )

    if isinstance(peer, types.PeerUser):
        return peer.user_id

    return None


# ============================================================
# VC TRACKER
# ============================================================

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

        # chat_id -> current participant IDs
        self.current_users = {}

        # chat_id -> reconciliation task
        self.tasks = {}

        # Prevent duplicate processing
        self.lock = asyncio.Lock()

        # Last discovery time
        self.last_discovery = {}

    # ========================================================
    # GROUP TITLE
    # ========================================================

    async def get_title(self, chat_id):

        if chat_id in self.titles:
            return self.titles[chat_id]

        try:

            chat = await self.client.get_chat(
                chat_id
            )

            title = (
                getattr(
                    chat,
                    "title",
                    None
                )
                or "Voice Chat"
            )

        except Exception as e:

            log.warning(
                "TITLE ERROR | group=%s | %s",
                chat_id,
                e
            )

            title = "Voice Chat"

        self.titles[chat_id] = title

        return title

    # ========================================================
    # USER
    # ========================================================

    async def get_user(
        self,
        user_id,
        users=None
    ):

        if users:

            user = users.get(
                user_id
            )

            if user:
                return user

        try:

            return await self.client.get_users(
                user_id
            )

        except Exception:

            return None

    # ========================================================
    # JOIN LOG
    # ========================================================

    async def handle_join(
        self,
        chat_id,
        user_id,
        user,
        join_time
    ):

        # Already active
        if get_active(
            user_id,
            chat_id
        ):

            return False

        title = await self.get_title(
            chat_id
        )

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

        safe_name = html.escape(
            name
        )

        username_text = (
            f"@{html.escape(username)}"
            if username
            else "No username"
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

            f"🎙️ <b>Group:</b> "
            f"{html.escape(title)}\n"

            f"🕐 <b>Joined:</b> "
            f"{format_time(join_time)}"
        )

        try:

            await self.log_func(
                text
            )

            log.info(
                "JOIN LOG SENT | "
                "group=%s | user=%s | join=%s",
                chat_id,
                user_id,
                join_time
            )

        except Exception as e:

            log.exception(
                "JOIN LOG SEND ERROR | %s",
                e
            )

        return True

    # ========================================================
    # LEAVE LOG
    # ========================================================

    async def handle_leave(
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
            return False

        leave_time = now()

        finished = end_session(
            user_id,
            chat_id,
            leave_time
        )

        if not finished:
            return False

        name = (
            get_name(user)
            if user
            else finished.get(
                "name",
                "Unknown User"
            )
        )

        username = (
            getattr(
                user,
                "username",
                None
            )
            if user
            else finished.get(
                "username"
            )
        )

        title = finished.get(
            "chat_title",
            "Voice Chat"
        )

        safe_name = html.escape(
            name
        )

        username_text = (
            f"@{html.escape(username)}"
            if username
            else "No username"
        )

        text = (
            "🔴 <b>VC USER LEFT</b>\n\n"

            f"👤 <b>Name:</b> {safe_name}\n"
            f"🔗 <b>Username:</b> {username_text}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"

            f"🎙️ <b>Group:</b> "
            f"{html.escape(title)}\n\n"

            f"🟢 <b>Joined:</b> "
            f"{format_time(finished['join_time'])}\n"

            f"🔴 <b>Left:</b> "
            f"{format_time(finished['leave_time'])}\n"

            f"⏱️ <b>Stayed:</b> "
            f"{format_duration(finished['duration_seconds'])}"
        )

        try:

            await self.log_func(
                text
            )

            log.info(
                "LEAVE LOG SENT | "
                "group=%s | user=%s | duration=%s",
                chat_id,
                user_id,
                finished["duration_seconds"]
            )

        except Exception as e:

            log.exception(
                "LEAVE LOG SEND ERROR | %s",
                e
            )

        return True

    # ========================================================
    # PROCESS RAW PARTICIPANT
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
                "PARTICIPANT CALL UNKNOWN | call=%s",
                call_id
            )
            return

        if not is_tracked(
            chat_id
        ):
            return

        user_id = get_user_id(
            participant
        )

        if not user_id:
            return

        user = await self.get_user(
            user_id,
            users
        )

        # ====================================================
        # LEAVE
        # ====================================================

        if getattr(
            participant,
            "left",
            False
        ):

            async with self.lock:

                await self.handle_leave(
                    chat_id,
                    user_id,
                    user
                )

            return

        # ====================================================
        # JOIN
        # ====================================================

        if getattr(
            participant,
            "just_joined",
            False
        ):

            join_time = telegram_time(
                getattr(
                    participant,
                    "date",
                    None
                )
            )

            async with self.lock:

                await self.handle_join(
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

        log.info(
            "PROCESSING PARTICIPANT BATCH | count=%s",
            len(participants)
        )

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
    # GET VC PARTICIPANTS
    # ========================================================

    async def get_participants(
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

        if not call_id:
            return None

        if not access_hash:

            log.warning(
                "NO ACCESS HASH | call=%s",
                call_id
            )

            return None

        try:

            input_call = types.InputGroupCall(
                id=call_id,
                access_hash=access_hash
            )

            result = await self.client.invoke(
                functions.phone.GetGroupParticipants(
                    call=input_call,
                    ids=[],
                    sources=[],
                    offset=0,
                    limit=100
                )
            )

            participants = getattr(
                result,
                "participants",
                None
            )

            if participants is None:
                return None

            log.info(
                "VC API PARTICIPANTS | "
                "call=%s | count=%s",
                call_id,
                len(participants)
            )

            return participants

        except FloodWait as e:

            log.warning(
                "FLOOD WAIT | %s seconds",
                e.value
            )

            await asyncio.sleep(
                e.value
            )

            return None

        except Exception as e:

            log.exception(
                "GET GROUP PARTICIPANTS ERROR | "
                "call=%s | %s",
                call_id,
                e
            )

            return None

    # ========================================================
    # RECONCILE
    # ========================================================

    async def reconcile(
        self,
        chat_id,
        call
    ):

        if not is_tracked(
            chat_id
        ):
            return

        participants = await self.get_participants(
            call
        )

        # VERY IMPORTANT:
        # API error par users ko LEFT mat mark karo.
        if participants is None:
            return

        current_ids = set()

        for participant in participants:

            user_id = get_user_id(
                participant
            )

            if not user_id:
                continue

            if getattr(
                participant,
                "left",
                False
            ):
                continue

            current_ids.add(
                user_id
            )

        log.info(
            "VC RECONCILE | "
            "group=%s | current=%s",
            chat_id,
            len(current_ids)
        )

        old_ids = self.current_users.get(
            chat_id
        )

        # First successful snapshot
        if old_ids is None:

            self.current_users[
                chat_id
            ] = current_ids

            # Recover users missed by raw update
            for participant in participants:

                user_id = get_user_id(
                    participant
                )

                if not user_id:
                    continue

                if get_active(
                    user_id,
                    chat_id
                ):
                    continue

                user = await self.get_user(
                    user_id
                )

                join_time = telegram_time(
                    getattr(
                        participant,
                        "date",
                        None
                    )
                )

                async with self.lock:

                    await self.handle_join(
                        chat_id,
                        user_id,
                        user,
                        join_time
                    )

            return

        joined = (
            current_ids - old_ids
        )

        left = (
            old_ids - current_ids
        )

        # ====================================================
        # JOINED
        # ====================================================

        for user_id in joined:

            if get_active(
                user_id,
                chat_id
            ):
                continue

            user = await self.get_user(
                user_id
            )

            async with self.lock:

                await self.handle_join(
                    chat_id,
                    user_id,
                    user,
                    now()
                )

        # ====================================================
        # LEFT
        # ====================================================

        for user_id in left:

            user = await self.get_user(
                user_id
            )

            async with self.lock:

                await self.handle_leave(
                    chat_id,
                    user_id,
                    user
                )

        self.current_users[
            chat_id
        ] = current_ids

    # ========================================================
    # START RECONCILIATION
    # ========================================================

    async def start_reconciliation(
        self,
        chat_id,
        call
    ):

        if chat_id in self.tasks:
            return

        async def worker():

            log.info(
                "RECONCILIATION STARTED | group=%s",
                chat_id
            )

            while is_tracked(
                chat_id
            ):

                try:

                    await self.reconcile(
                        chat_id,
                        call
                    )

                except Exception as e:

                    log.exception(
                        "RECONCILIATION ERROR | %s",
                        e
                    )

                await asyncio.sleep(
                    3
                )

            log.info(
                "RECONCILIATION STOPPED | group=%s",
                chat_id
            )

        self.tasks[
            chat_id
        ] = asyncio.create_task(
            worker()
        )

    # ========================================================
    # STOP RECONCILIATION
    # ========================================================

    async def stop_reconciliation(
        self,
        chat_id
    ):

        task = self.tasks.pop(
            chat_id,
            None
        )

        if task:

            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

        self.current_users.pop(
            chat_id,
            None
        )

    # ========================================================
    # CLOSE VC
    # ========================================================

    async def close_call(
        self,
        chat_id
    ):

        log.info(
            "VC CLOSED | group=%s",
            chat_id
        )

        active_users = get_active_for_chat(
            chat_id
        )

        for session in active_users:

            user_id = session.get(
                "user_id"
            )

            if user_id:

                try:

                    await self.handle_leave(
                        chat_id,
                        user_id
                    )

                except Exception as e:

                    log.exception(
                        "VC CLOSE LEAVE ERROR | %s",
                        e
                    )

        self.current_users.pop(
            chat_id,
            None
        )

    # ========================================================
    # RAW UPDATE
    # ========================================================

    async def raw_update(
        self,
        update,
        users,
        chats
    ):

        # ====================================================
        # UPDATE GROUP CALL
        # ====================================================

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

            call_id = getattr(
                call,
                "id",
                None
            )

            log.info(
                "🔥 GROUP CALL UPDATE | "
                "raw_chat=%s | chat=%s | call=%s",
                raw_chat_id,
                chat_id,
                call_id
            )

            # VC ended
            if isinstance(
                call,
                types.GroupCallDiscarded
            ):

                await self.close_call(
                    chat_id
                )

                self.calls.pop(
                    call_id,
                    None
                )

                return

            if not is_tracked(
                chat_id
            ):

                log.info(
                    "VC UPDATE IGNORED | "
                    "group not tracked=%s",
                    chat_id
                )

                return

            if call_id:

                self.calls[
                    call_id
                ] = chat_id

                log.info(
                    "✅ CALL REGISTERED | "
                    "call=%s | group=%s",
                    call_id,
                    chat_id
                )

                await self.reconcile(
                    chat_id,
                    call
                )

                await self.start_reconciliation(
                    chat_id,
                    call
                )

            return

        # ====================================================
        # UPDATE GROUP CALL PARTICIPANTS
        # ====================================================

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
                "🔥 GROUP CALL PARTICIPANTS | "
                "call=%s | count=%s",
                call_id,
                len(participants)
            )

            if not call_id:
                return

            chat_id = self.calls.get(
                call_id
            )

            if not chat_id:

                log.warning(
                    "⚠️ UNKNOWN CALL | "
                    "call=%s | participant update ignored",
                    call_id
                )

                return

            await self.participant_batch(
                call,
                participants,
                users
            )

            # Immediately reconcile after raw update
            try:

                await self.reconcile(
                    chat_id,
                    call
                )

            except Exception as e:

                log.exception(
                    "POST UPDATE RECONCILE ERROR | %s",
                    e
                )

            return

        # ====================================================
        # EVERYTHING ELSE
        # ====================================================

        log.debug(
            "OTHER RAW UPDATE | %s",
            type(update).__name__
        )
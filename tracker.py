import asyncio
import html
import logging
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
    get_tracked_groups,
)

log = logging.getLogger("VC-TRACKER")


# ============================================================
# TIME HELPERS
# ============================================================

def now():
    return datetime.now(timezone.utc)


def tg_time(timestamp):
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
    if not dt:
        return "Unknown"

    try:
        return dt.astimezone().strftime(
            "%d-%m-%Y %I:%M:%S %p"
        )
    except Exception:
        return "Unknown"


def format_duration(seconds):
    seconds = max(0, int(seconds or 0))

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


# ============================================================
# USER HELPERS
# ============================================================

def get_name(user):

    if not user:
        return "Unknown User"

    first = getattr(user, "first_name", "") or ""
    last = getattr(user, "last_name", "") or ""

    name = f"{first} {last}".strip()

    return name or "Unknown User"


def participant_user_id(participant):

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

        # chat_id -> GroupCall
        self.call_objects = {}

        # chat_id -> set(user_id)
        self.users = {}

        # background tasks
        self.tasks = {}

        # chat_id -> title
        self.titles = {}

        self.lock = asyncio.Lock()

    # ========================================================
    # GROUP TITLE
    # ========================================================

    async def get_title(self, chat_id):

        if chat_id in self.titles:
            return self.titles[chat_id]

        title = None

        try:
            chat = await self.client.get_chat(chat_id)

            title = (
                getattr(chat, "title", None)
                or getattr(chat, "first_name", None)
                or getattr(chat, "username", None)
            )

        except Exception as e:

            log.warning(
                "GROUP TITLE ERROR | group=%s | %s",
                chat_id,
                e
            )

        if not title:
            title = "Unknown Group"

        self.titles[chat_id] = title

        log.info(
            "GROUP TITLE | group=%s | title=%s",
            chat_id,
            title
        )

        return title

    # ========================================================
    # GET USER
    # ========================================================

    async def get_user(
        self,
        user_id,
        users=None
    ):

        if users:

            try:
                user = users.get(user_id)

                if user:
                    return user

            except Exception:
                pass

        try:

            return await self.client.get_users(
                user_id
            )

        except Exception as e:

            log.debug(
                "GET USER ERROR | user=%s | %s",
                user_id,
                e
            )

            return None

    # ========================================================
    # JOIN
    # ========================================================

    async def process_join(
        self,
        chat_id,
        user_id,
        user,
        join_time
    ):

        if not user_id:
            return

        # Duplicate JOIN ignore
        if get_active(
            user_id,
            chat_id
        ):
            log.debug(
                "DUPLICATE JOIN IGNORED | group=%s | user=%s",
                chat_id,
                user_id
            )
            return

        title = await self.get_title(
            chat_id
        )

        name = get_name(
            user
        )

        username = (
            getattr(user, "username", None)
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

        # ----------------------------------------------------
        # SAVE ACTIVE SESSION
        # ----------------------------------------------------

        try:

            start_session(
                chat_id=chat_id,
                user_id=user_id,
                user_name=name,
                username=username,
                join_time=join_time
            )

        except Exception as e:

            log.exception(
                "START SESSION ERROR | group=%s | user=%s | %s",
                chat_id,
                user_id,
                e
            )

            return

        # ----------------------------------------------------
        # JOIN LOG
        # ----------------------------------------------------

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
                "🟢 JOIN LOG SENT | group=%s | user=%s",
                chat_id,
                user_id
            )

        except Exception as e:

            log.exception(
                "JOIN LOG ERROR | group=%s | user=%s | %s",
                chat_id,
                user_id,
                e
            )

    # ========================================================
    # LEAVE
    # ========================================================

    async def process_leave(
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

            log.warning(
                "⚠️ LEAVE WITHOUT ACTIVE SESSION | "
                "group=%s | user=%s",
                chat_id,
                user_id
            )

            return

        leave_time = now()

        try:

            finished = end_session(
                chat_id=chat_id,
                user_id=user_id,
                leave_time=leave_time
            )

        except Exception as e:

            log.exception(
                "END SESSION ERROR | group=%s | user=%s | %s",
                chat_id,
                user_id,
                e
            )

            return

        if not finished:
            return

        name = (
            get_name(user)
            if user
            else finished.get(
                "user_name",
                "Unknown User"
            )
        )

        username = (
            getattr(user, "username", None)
            if user
            else finished.get("username")
        )

        title = await self.get_title(
            chat_id
        )

        safe_name = html.escape(
            name
        )

        username_text = (
            f"@{html.escape(username)}"
            if username
            else "No username"
        )

        duration = finished.get(
            "duration",
            0
        )

        text = (
            "🔴 <b>VC USER LEFT</b>\n\n"

            f"👤 <b>Name:</b> {safe_name}\n"
            f"🔗 <b>Username:</b> {username_text}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"

            f"🎙️ <b>Group:</b> "
            f"{html.escape(title)}\n\n"

            f"🟢 <b>Joined:</b> "
            f"{format_time(finished.get('join_time'))}\n"

            f"🔴 <b>Left:</b> "
            f"{format_time(finished.get('leave_time'))}\n"

            f"⏱️ <b>Stayed:</b> "
            f"{format_duration(duration)}"
        )

        try:

            await self.log_func(
                text
            )

            log.info(
                "🔴 LEAVE LOG SENT | "
                "group=%s | user=%s | duration=%s",
                chat_id,
                user_id,
                duration
            )

        except Exception as e:

            log.exception(
                "LEAVE LOG ERROR | %s",
                e
            )

    # ========================================================
    # FETCH PARTICIPANTS
    # ========================================================

    async def fetch_participants(
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
                "CALL HAS NO ID/ACCESS HASH | call=%s",
                call
            )

            return None, {}

        result_users = {}
        result_participants = []

        offset = ""

        try:

            while True:

                result = await self.client.invoke(
                    functions.phone.GetGroupParticipants(
                        call=types.InputGroupCall(
                            id=call_id,
                            access_hash=access_hash
                        ),
                        ids=[],
                        sources=[],
                        offset=offset,
                        limit=100
                    )
                )

                page = getattr(
                    result,
                    "participants",
                    []
                )

                users = getattr(
                    result,
                    "users",
                    []
                )

                for user in users:

                    uid = getattr(
                        user,
                        "id",
                        None
                    )

                    if uid:
                        result_users[uid] = user

                result_participants.extend(
                    page
                )

                next_offset = getattr(
                    result,
                    "next_offset",
                    ""
                )

                if not next_offset:
                    break

                offset = next_offset

            log.info(
                "✅ VC LIST FETCHED | "
                "call=%s | participants=%s",
                call_id,
                len(result_participants)
            )

            return (
                result_participants,
                result_users
            )

        except FloodWait as e:

            log.warning(
                "FLOOD WAIT | %s",
                e.value
            )

            await asyncio.sleep(
                e.value
            )

            return None, {}

        except Exception as e:

            log.exception(
                "GET GROUP PARTICIPANTS ERROR | %s",
                e
            )

            return None, {}

    # ========================================================
    # RECONCILE
    # ========================================================

    async def reconcile(
        self,
        chat_id,
        call
    ):

        if not is_tracked(chat_id):
            return

        participants, users = await self.fetch_participants(
            call
        )

        if participants is None:
            return

        current = {}

        for participant in participants:

            user_id = participant_user_id(
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

            current[user_id] = participant

        current_ids = set(
            current.keys()
        )

        old_ids = self.users.get(
            chat_id
        )

        # ====================================================
        # FIRST SNAPSHOT
        # ====================================================

        if old_ids is None:

            self.users[
                chat_id
            ] = current_ids

            log.info(
                "📸 INITIAL VC SNAPSHOT | "
                "group=%s | users=%s",
                chat_id,
                len(current_ids)
            )

            for user_id, participant in current.items():

                if get_active(
                    user_id,
                    chat_id
                ):
                    continue

                user = await self.get_user(
                    user_id,
                    users
                )

                join_time = tg_time(
                    getattr(
                        participant,
                        "date",
                        None
                    )
                )

                async with self.lock:

                    await self.process_join(
                        chat_id,
                        user_id,
                        user,
                        join_time
                    )

            return

        # ====================================================
        # JOINED
        # ====================================================

        joined = (
            current_ids - old_ids
        )

        if joined:

            log.info(
                "🟢 NEW VC USERS | group=%s | users=%s",
                chat_id,
                list(joined)
            )

        for user_id in joined:

            participant = current.get(
                user_id
            )

            if not participant:
                continue

            user = await self.get_user(
                user_id,
                users
            )

            join_time = tg_time(
                getattr(
                    participant,
                    "date",
                    None
                )
            )

            async with self.lock:

                await self.process_join(
                    chat_id,
                    user_id,
                    user,
                    join_time
                )

        # ====================================================
        # LEFT
        # ====================================================

        left = (
            old_ids - current_ids
        )

        if left:

            log.info(
                "🔴 VC LEFT USERS | group=%s | users=%s",
                chat_id,
                list(left)
            )

        for user_id in left:

            user = await self.get_user(
                user_id
            )

            async with self.lock:

                await self.process_leave(
                    chat_id,
                    user_id,
                    user
                )

        self.users[
            chat_id
        ] = current_ids

        if joined or left:

            log.info(
                "🔄 VC CHANGED | "
                "group=%s | joined=%s | left=%s",
                chat_id,
                list(joined),
                list(left)
            )

    # ========================================================
    # RAW PARTICIPANTS
    # ========================================================

    async def process_raw_participants(
        self,
        chat_id,
        participants,
        users
    ):

        log.info(
            "👥 PROCESSING RAW PARTICIPANTS | "
            "group=%s | count=%s",
            chat_id,
            len(participants)
        )

        for participant in participants:

            user_id = participant_user_id(
                participant
            )

            if not user_id:
                continue

            user = await self.get_user(
                user_id,
                users
            )

            # ------------------------------------------------
            # LEFT
            # ------------------------------------------------

            if getattr(
                participant,
                "left",
                False
            ):

                log.info(
                    "🔴 RAW LEFT DETECTED | "
                    "group=%s | user=%s",
                    chat_id,
                    user_id
                )

                async with self.lock:

                    await self.process_leave(
                        chat_id,
                        user_id,
                        user
                    )

            # ------------------------------------------------
            # JOINED
            # ------------------------------------------------

            elif getattr(
                participant,
                "just_joined",
                False
            ):

                join_time = tg_time(
                    getattr(
                        participant,
                        "date",
                        None
                    )
                )

                log.info(
                    "🟢 RAW JOIN DETECTED | "
                    "group=%s | user=%s",
                    chat_id,
                    user_id
                )

                async with self.lock:

                    await self.process_join(
                        chat_id,
                        user_id,
                        user,
                        join_time
                    )

    # ========================================================
    # RECONCILIATION LOOP
    # ========================================================

    async def reconcile_loop(
        self,
        chat_id
    ):

        log.info(
            "🔄 RECONCILIATION STARTED | group=%s",
            chat_id
        )

        while is_tracked(chat_id):

            call = self.call_objects.get(
                chat_id
            )

            if call:

                try:

                    await self.reconcile(
                        chat_id,
                        call
                    )

                except Exception as e:

                    log.exception(
                        "RECONCILE ERROR | group=%s | %s",
                        chat_id,
                        e
                    )

            await asyncio.sleep(
                3
            )

        log.info(
            "RECONCILIATION STOPPED | group=%s",
            chat_id
        )

    async def start_reconciliation(
        self,
        chat_id
    ):

        key = f"reconcile:{chat_id}"

        task = self.tasks.get(
            key
        )

        if task and not task.done():
            return

        self.tasks[
            key
        ] = asyncio.create_task(
            self.reconcile_loop(
                chat_id
            )
        )

    # ========================================================
    # DISCOVER ACTIVE VC
    # ========================================================

    async def discover_call(
        self,
        chat_id
    ):

        if not is_tracked(chat_id):
            return

        try:

            log.info(
                "🔎 CHECKING VC | group=%s",
                chat_id
            )

            peer = await self.client.resolve_peer(
                chat_id
            )

            input_call = None

            # ------------------------------------------------
            # CHANNEL / SUPERGROUP
            # ------------------------------------------------

            if isinstance(
                peer,
                types.InputPeerChannel
            ):

                input_channel = types.InputChannel(
                    channel_id=peer.channel_id,
                    access_hash=peer.access_hash
                )

                full = await self.client.invoke(
                    functions.channels.GetFullChannel(
                        channel=input_channel
                    )
                )

                full_chat = getattr(
                    full,
                    "full_chat",
                    None
                )

                call = getattr(
                    full_chat,
                    "call",
                    None
                )

                if call:

                    input_call = types.InputGroupCall(
                        id=call.id,
                        access_hash=call.access_hash
                    )

            # ------------------------------------------------
            # NORMAL GROUP
            # ------------------------------------------------

            elif isinstance(
                peer,
                types.InputPeerChat
            ):

                full = await self.client.invoke(
                    functions.messages.GetFullChat(
                        chat_id=peer.chat_id
                    )
                )

                full_chat = getattr(
                    full,
                    "full_chat",
                    None
                )

                call = getattr(
                    full_chat,
                    "call",
                    None
                )

                if call:

                    input_call = types.InputGroupCall(
                        id=call.id,
                        access_hash=call.access_hash
                    )

            if not input_call:

                log.debug(
                    "NO ACTIVE VC | group=%s",
                    chat_id
                )

                return

            result = await self.client.invoke(
                functions.phone.GetGroupCall(
                    call=input_call,
                    limit=100
                )
            )

            call = getattr(
                result,
                "call",
                None
            )

            if not call:
                return

            call_id = getattr(
                call,
                "id",
                None
            )

            if not call_id:
                return

            # ------------------------------------------------
            # REGISTER CALL
            # ------------------------------------------------

            self.calls[
                call_id
            ] = chat_id

            self.call_objects[
                chat_id
            ] = call

            await self.get_title(
                chat_id
            )

            log.info(
                "✅ ACTIVE VC DISCOVERED | "
                "group=%s | call=%s",
                chat_id,
                call_id
            )

            await self.reconcile(
                chat_id,
                call
            )

            await self.start_reconciliation(
                chat_id
            )

        except FloodWait as e:

            log.warning(
                "DISCOVERY FLOOD WAIT | %s",
                e.value
            )

        except Exception as e:

            log.debug(
                "DISCOVER CALL ERROR | "
                "group=%s | %s",
                chat_id,
                e
            )

    # ========================================================
    # DISCOVERY LOOP
    # ========================================================

    async def discovery_loop(self):

        log.info(
            "🔎 VC AUTO DISCOVERY LOOP RUNNING"
        )

        while True:

            try:

                groups = get_tracked_groups()

                log.debug(
                    "TRACKED GROUPS FOUND | count=%s",
                    len(groups)
                )

                for group in groups:

                    chat_id = group.get(
                        "chat_id"
                    )

                    if not chat_id:
                        continue

                    await self.discover_call(
                        chat_id
                    )

            except asyncio.CancelledError:

                return

            except Exception as e:

                log.exception(
                    "DISCOVERY LOOP ERROR | %s",
                    e
                )

            await asyncio.sleep(
                5
            )

    # ========================================================
    # START
    # ========================================================

    async def start(self):

        task = self.tasks.get(
            "discovery"
        )

        if task and not task.done():
            return

        self.tasks[
            "discovery"
        ] = asyncio.create_task(
            self.discovery_loop()
        )

        log.info(
            "🚀 VC DISCOVERY LOOP STARTED"
        )

    # ========================================================
    # STOP
    # ========================================================

    async def stop(self):

        for task in list(
            self.tasks.values()
        ):

            task.cancel()

        for task in list(
            self.tasks.values()
        ):

            try:

                await task

            except asyncio.CancelledError:

                pass

        self.tasks.clear()

        log.info(
            "🛑 VC TRACKER STOPPED"
        )

    # ========================================================
    # CLOSE VC
    # ========================================================

    async def close_call(
        self,
        chat_id
    ):

        active = get_active_for_chat(
            chat_id
        )

        log.info(
            "🔴 VC CLOSED | "
            "group=%s | active=%s",
            chat_id,
            len(active)
        )

        for session in active:

            user_id = session.get(
                "user_id"
            )

            if not user_id:
                continue

            try:

                await self.process_leave(
                    chat_id,
                    user_id
                )

            except Exception as e:

                log.exception(
                    "CLOSE VC LEAVE ERROR | %s",
                    e
                )

        # Remove call mapping
        for call_id, mapped_chat in list(
            self.calls.items()
        ):

            if mapped_chat == chat_id:
                self.calls.pop(
                    call_id,
                    None
                )

        self.users.pop(
            chat_id,
            None
        )

        self.call_objects.pop(
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

        update_name = type(
            update
        ).__name__

        log.info(
            "📡 TRACKER RAW UPDATE | %s",
            update_name
        )

        # ====================================================
        # GROUP CALL
        # ====================================================

        if isinstance(
            update,
            types.UpdateGroupCall
        ):

            chat_id = getattr(
                update,
                "chat_id",
                None
            )

            call = getattr(
                update,
                "call",
                None
            )

            call_id = getattr(
                call,
                "id",
                None
            )

            log.info(
                "🎙️ GROUP CALL UPDATE | "
                "group=%s | call=%s",
                chat_id,
                call_id
            )

            if chat_id is None:

                log.error(
                    "❌ UpdateGroupCall HAS NO CHAT ID"
                )

                return

            # ------------------------------------------------
            # VC CLOSED
            # ------------------------------------------------

            if isinstance(
                call,
                types.GroupCallDiscarded
            ):

                log.info(
                    "🔴 GROUP CALL DISCARDED | group=%s",
                    chat_id
                )

                await self.close_call(
                    chat_id
                )

                return

            if not is_tracked(
                chat_id
            ):

                log.info(
                    "VC NOT TRACKED | group=%s",
                    chat_id
                )

                return

            if not call_id:
                return

            # ------------------------------------------------
            # REGISTER
            # ------------------------------------------------

            self.calls[
                call_id
            ] = chat_id

            self.call_objects[
                chat_id
            ] = call

            await self.get_title(
                chat_id
            )

            log.info(
                "✅ CALL REGISTERED | "
                "group=%s | call=%s",
                chat_id,
                call_id
            )

            await self.reconcile(
                chat_id,
                call
            )

            await self.start_reconciliation(
                chat_id
            )

            return

        # ====================================================
        # GROUP CALL PARTICIPANTS
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

            version = getattr(
                update,
                "version",
                None
            )

            call_id = getattr(
                call,
                "id",
                None
            )

            log.info(
                "🎙️ PARTICIPANT UPDATE | "
                "call=%s | count=%s | version=%s",
                call_id,
                len(participants),
                version
            )

            if not call_id:
                return

            # ------------------------------------------------
            # FIND GROUP
            # ------------------------------------------------

            chat_id = self.calls.get(
                call_id
            )

            if not chat_id:

                # Try existing call objects
                for known_chat_id, known_call in list(
                    self.call_objects.items()
                ):

                    known_call_id = getattr(
                        known_call,
                        "id",
                        None
                    )

                    if known_call_id == call_id:

                        chat_id = known_chat_id

                        self.calls[
                            call_id
                        ] = chat_id

                        break

            if not chat_id:

                log.warning(
                    "⚠️ UNKNOWN VC CALL | call=%s",
                    call_id
                )

                return

            if not is_tracked(
                chat_id
            ):
                return

            self.call_objects[
                chat_id
            ] = call

            # ------------------------------------------------
            # RAW JOIN / LEAVE
            # ------------------------------------------------

            await self.process_raw_participants(
                chat_id,
                participants,
                users
            )

            # ------------------------------------------------
            # RECONCILE
            # ------------------------------------------------

            await self.reconcile(
                chat_id,
                call
            )

            return

        # ====================================================
        # OTHER RAW UPDATES
        # ====================================================

        log.debug(
            "RAW UPDATE IGNORED | %s",
            update_name
        )
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

    first = getattr(user, "first_name", "") or ""
    last = getattr(user, "last_name", "") or ""

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

        # chat_id -> InputGroupCall
        self.call_objects = {}

        # chat_id -> title
        self.titles = {}

        # chat_id -> current VC user IDs
        self.current_users = {}

        # chat_id -> last reconciliation task
        self.tasks = {}

        self.lock = asyncio.Lock()

    # ========================================================
    # TITLE
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

        except Exception:

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
    # JOIN
    # ========================================================

    async def handle_join(
        self,
        chat_id,
        user_id,
        user,
        join_time
    ):

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
                "JOIN LOG SENT | user=%s | group=%s",
                user_id,
                chat_id
            )

        except Exception as e:

            log.exception(
                "JOIN LOG FAILED | %s",
                e
            )

        return True

    # ========================================================
    # LEAVE
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
                "LEAVE LOG SENT | user=%s | group=%s",
                user_id,
                chat_id
            )

        except Exception as e:

            log.exception(
                "LEAVE LOG FAILED | %s",
                e
            )

        return True

    # ========================================================
    # FETCH ALL VC PARTICIPANTS
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
            return None, {}

        all_participants = []
        all_users = {}

        # IMPORTANT:
        # Telegram expects offset as STRING.
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

                result_users = getattr(
                    result,
                    "users",
                    []
                )

                for user in result_users:

                    user_id = getattr(
                        user,
                        "id",
                        None
                    )

                    if user_id:
                        all_users[
                            user_id
                        ] = user

                all_participants.extend(
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
                "VC PARTICIPANTS FETCHED | "
                "call=%s | users=%s",
                call_id,
                len(all_participants)
            )

            return (
                all_participants,
                all_users
            )

        except FloodWait as e:

            log.warning(
                "FLOOD WAIT | %s seconds",
                e.value
            )

            await asyncio.sleep(
                e.value
            )

            return None, {}

        except Exception as e:

            log.exception(
                "GET VC PARTICIPANTS ERROR | %s",
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

        if not is_tracked(
            chat_id
        ):
            return

        participants, users = (
            await self.fetch_participants(
                call
            )
        )

        # API error.
        # Never mark everybody LEFT.
        if participants is None:
            return

        current_ids = set()

        participant_map = {}

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

            participant_map[
                user_id
            ] = participant

        old_ids = self.current_users.get(
            chat_id
        )

        # ====================================================
        # FIRST SNAPSHOT
        # ====================================================

        if old_ids is None:

            log.info(
                "INITIAL VC SNAPSHOT | "
                "group=%s | users=%s",
                chat_id,
                len(current_ids)
            )

            self.current_users[
                chat_id
            ] = current_ids

            for user_id in current_ids:

                if get_active(
                    user_id,
                    chat_id
                ):
                    continue

                user = await self.get_user(
                    user_id,
                    users
                )

                participant = participant_map[
                    user_id
                ]

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

        # ====================================================
        # JOIN
        # ====================================================

        joined = (
            current_ids - old_ids
        )

        for user_id in joined:

            if get_active(
                user_id,
                chat_id
            ):
                continue

            user = await self.get_user(
                user_id,
                users
            )

            participant = participant_map[
                user_id
            ]

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

        # ====================================================
        # LEAVE
        # ====================================================

        left = (
            old_ids - current_ids
        )

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
    # DISCOVER ACTIVE VC
    # ========================================================

    async def discover_group_call(
        self,
        chat_id
    ):

        if not is_tracked(
            chat_id
        ):
            return

        try:

            peer = await self.client.resolve_peer(
                chat_id
            )

            full = None

            # ----------------------------------------------
            # Supergroup
            # ----------------------------------------------

            if isinstance(
                peer,
                types.InputPeerChannel
            ):

                channel = types.InputChannel(
                    channel_id=peer.channel_id,
                    access_hash=peer.access_hash
                )

                full = await self.client.invoke(
                    functions.channels.GetFullChannel(
                        channel=channel
                    )
                )

            # ----------------------------------------------
            # Basic group
            # ----------------------------------------------

            elif isinstance(
                peer,
                types.InputPeerChat
            ):

                full = await self.client.invoke(
                    functions.messages.GetFullChat(
                        chat_id=peer.chat_id
                    )
                )

            if not full:
                return

            full_chat = getattr(
                full,
                "full_chat",
                None
            )

            if not full_chat:
                return

            call = getattr(
                full_chat,
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

            old_call = self.call_objects.get(
                chat_id
            )

            old_id = getattr(
                old_call,
                "id",
                None
            )

            if old_id != call_id:

                log.info(
                    "🔎 ACTIVE VC DISCOVERED | "
                    "group=%s | call=%s",
                    chat_id,
                    call_id
                )

            self.calls[
                call_id
            ] = chat_id

            self.call_objects[
                chat_id
            ] = call

            await self.get_title(
                chat_id
            )

            await self.start_reconciliation(
                chat_id,
                call
            )

        except FloodWait as e:

            log.warning(
                "VC DISCOVERY FLOOD WAIT | %s",
                e.value
            )

        except Exception as e:

            log.debug(
                "VC DISCOVERY ERROR | group=%s | %s",
                chat_id,
                e
            )

    # ========================================================
    # DISCOVER ALL TRACKED GROUPS
    # ========================================================

    async def discovery_loop(self):

        while True:

            try:

                groups = get_tracked_groups()

                for group in groups:

                    chat_id = group.get(
                        "chat_id"
                    )

                    if chat_id:

                        await self.discover_group_call(
                            chat_id
                        )

            except asyncio.CancelledError:
                break

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

        if "discovery" in self.tasks:
            return

        log.info(
            "VC DISCOVERY STARTED"
        )

        self.tasks[
            "discovery"
        ] = asyncio.create_task(
            self.discovery_loop()
        )

    # ========================================================
    # STOP
    # ========================================================

    async def stop(self):

        for key, task in list(
            self.tasks.items()
        ):

            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

        self.tasks.clear()

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
        # NEW / UPDATED VC
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

            # MTProto channel ID -> Pyrogram/Telegram chat ID
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
                "group=%s | call=%s",
                chat_id,
                call_id
            )

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

                self.call_objects.pop(
                    chat_id,
                    None
                )

                self.current_users.pop(
                    chat_id,
                    None
                )

                return

            if not is_tracked(
                chat_id
            ):
                return

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
                "✅ VC REGISTERED | "
                "group=%s | call=%s",
                chat_id,
                call_id
            )

            await self.reconcile(
                chat_id,
                call
            )

            return

        # ====================================================
        # PARTICIPANT UPDATE
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

            version = getattr(
                update,
                "version",
                None
            )

            log.info(
                "🔥 VC PARTICIPANTS UPDATE | "
                "call=%s | count=%s | version=%s",
                call_id,
                len(participants),
                version
            )

            chat_id = self.calls.get(
                call_id
            )

            if not chat_id:

                log.warning(
                    "⚠️ CALL NOT MAPPED | call=%s",
                    call_id
                )

                return

            # Raw immediate processing
            for participant in participants:

                try:

                    await self.participant(
                        call,
                        participant,
                        users
                    )

                except Exception as e:

                    log.exception(
                        "PARTICIPANT PROCESSING ERROR | %s",
                        e
                    )

            # Re-fetch complete list.
            # Telegram specifically recommends
            # phone.getGroupParticipants when versions
            # are missed. 
            await self.reconcile(
                chat_id,
                self.call_objects.get(
                    chat_id,
                    call
                )
            )

            return

    # ========================================================
    # RAW PARTICIPANT
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

        chat_id = self.calls.get(
            call_id
        )

        if not chat_id:
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

        # JOIN
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

        # LEAVE
        elif getattr(
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

    # ========================================================
    # CLOSE VC
    # ========================================================

    async def close_call(
        self,
        chat_id
    ):

        log.info(
            "🔴 VC CLOSED | group=%s",
            chat_id
        )

        active = get_active_for_chat(
            chat_id
        )

        for session in active:

            user_id = session.get(
                "user_id"
            )

            if not user_id:
                continue

            try:

                await self.handle_leave(
                    chat_id,
                    user_id
                )

            except Exception as e:

                log.exception(
                    "CLOSE VC LEAVE ERROR | %s",
                    e
                )
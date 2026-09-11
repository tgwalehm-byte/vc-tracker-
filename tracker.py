import asyncio
import logging

from datetime import datetime, timezone

from pyrogram.raw import types, functions

from database import (
    is_tracked,
    start_session,
    get_active,
    get_active_for_chat,
    finish_session,
)

log = logging.getLogger(__name__)


class VCTracker:

    def __init__(
        self,
        client,
        send_log,
        poll_seconds=5
    ):

        self.client = client
        self.send_log = send_log

        self.poll_seconds = poll_seconds

        # call_id -> information
        self.calls = {}

        # chat_id -> call_id
        self.chat_calls = {}

        self.lock = asyncio.Lock()

        self.running = True


    # ---------------------------------
    # TIME
    # ---------------------------------

    @staticmethod
    def now():

        return datetime.now(
            timezone.utc
        )


    @staticmethod
    def format_time(dt):

        return dt.astimezone().strftime(
            "%d-%m-%Y %I:%M:%S %p"
        )


    @staticmethod
    def format_duration(seconds):

        seconds = int(seconds)

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


    # ---------------------------------
    # GROUP TITLE
    # ---------------------------------

    async def get_title(
        self,
        chat_id
    ):

        try:

            chat = await self.client.get_chat(
                chat_id
            )

            return (
                chat.title
                or "Voice Chat"
            )

        except Exception:

            return "Voice Chat"


    # ---------------------------------
    # USER INFO
    # ---------------------------------

    async def get_user_info(
        self,
        user_id,
        users=None
    ):

        user = None

        if isinstance(users, dict):

            user = users.get(
                user_id
            )

        if user is None:

            try:

                user = await self.client.get_users(
                    user_id
                )

            except Exception:

                pass

        if user is None:

            return (
                "Unknown User",
                None
            )

        name = (
            user.first_name
            or ""
        )

        if user.last_name:

            name += (
                f" {user.last_name}"
            )

        name = (
            name.strip()
            or "Unknown User"
        )

        username = getattr(
            user,
            "username",
            None
        )

        return (
            name,
            username
        )


    # ---------------------------------
    # JOIN LOG
    # ---------------------------------

    async def join_log(
        self,
        data
    ):

        username = (
            f"@{data['username']}"
            if data.get("username")
            else "No username"
        )

        text = (
            "🟢 <b>VC USER JOINED</b>\n\n"

            f"👤 <b>Name:</b> "
            f"{data['name']}\n"

            f"🔗 <b>Username:</b> "
            f"{username}\n"

            f"🆔 <b>ID:</b> "
            f"<code>{data['user_id']}</code>\n\n"

            f"🎙️ <b>Group:</b> "
            f"{data['chat_title']}\n"

            f"🕐 <b>Joined:</b> "
            f"{self.format_time(data['join_time'])}"
        )

        await self.send_log(
            text
        )


    # ---------------------------------
    # LEFT LOG
    # ---------------------------------

    async def leave_log(
        self,
        data
    ):

        username = (
            f"@{data['username']}"
            if data.get("username")
            else "No username"
        )

        text = (
            "🔴 <b>VC USER LEFT</b>\n\n"

            f"👤 <b>Name:</b> "
            f"{data['name']}\n"

            f"🔗 <b>Username:</b> "
            f"{username}\n"

            f"🆔 <b>ID:</b> "
            f"<code>{data['user_id']}</code>\n\n"

            f"🎙️ <b>Group:</b> "
            f"{data['chat_title']}\n\n"

            f"🟢 <b>Joined:</b> "
            f"{self.format_time(data['join_time'])}\n"

            f"🔴 <b>Left:</b> "
            f"{self.format_time(data['leave_time'])}\n\n"

            f"⏱️ <b>Stayed:</b> "
            f"{self.format_duration(data['duration_seconds'])}"
        )

        await self.send_log(
            text
        )


    # ---------------------------------
    # PROCESS JOIN
    # ---------------------------------

    async def process_join(
        self,
        chat_id,
        user_id,
        join_time=None,
        users=None,
        title=None
    ):

        if not is_tracked(
            chat_id
        ):
            return

        # Already active
        if get_active(
            user_id,
            chat_id
        ):
            return

        name, username = (
            await self.get_user_info(
                user_id,
                users
            )
        )

        if join_time is None:

            join_time = self.now()

        if title is None:

            title = (
                await self.get_title(
                    chat_id
                )
            )

        start_session(
            user_id=user_id,
            name=name,
            username=username,
            chat_id=chat_id,
            chat_title=title,
            join_time=join_time
        )

        data = get_active(
            user_id,
            chat_id
        )

        if data:

            await self.join_log(
                data
            )

            log.info(
                "VC JOIN | user=%s chat=%s",
                user_id,
                chat_id
            )


    # ---------------------------------
    # PROCESS LEAVE
    # ---------------------------------

    async def process_leave(
        self,
        chat_id,
        user_id
    ):

        if not is_tracked(
            chat_id
        ):
            return

        if not get_active(
            user_id,
            chat_id
        ):
            return

        finished = finish_session(
            user_id,
            chat_id,
            self.now()
        )

        if finished:

            await self.leave_log(
                finished
            )

            log.info(
                "VC LEFT | user=%s chat=%s duration=%s",
                user_id,
                chat_id,
                finished["duration_seconds"]
            )


    # ---------------------------------
    # PEER -> USER ID
    # ---------------------------------

    @staticmethod
    def peer_id(peer):

        if isinstance(
            peer,
            types.PeerUser
        ):

            return peer.user_id

        return None


    # ---------------------------------
    # PARTICIPANTS
    # ---------------------------------

    async def reconcile(
        self,
        chat_id,
        call,
        participants,
        users
    ):

        if not is_tracked(
            chat_id
        ):
            return

        title = self.calls.get(
            call.id,
            {}
        ).get(
            "title",
            "Voice Chat"
        )

        current_users = set()

        for participant in participants:

            user_id = self.peer_id(
                participant.peer
            )

            if not user_id:
                continue

            left = bool(
                getattr(
                    participant,
                    "left",
                    False
                )
            )

            if left:

                await self.process_leave(
                    chat_id,
                    user_id
                )

                continue

            current_users.add(
                user_id
            )

            timestamp = getattr(
                participant,
                "date",
                None
            )

            join_time = None

            if timestamp:

                try:

                    join_time = (
                        datetime.fromtimestamp(
                            timestamp,
                            timezone.utc
                        )
                    )

                except Exception:

                    join_time = None

            if not get_active(
                user_id,
                chat_id
            ):

                await self.process_join(
                    chat_id=chat_id,
                    user_id=user_id,
                    join_time=join_time,
                    users=users,
                    title=title
                )

        # --------------------------------
        # Detect missing users = LEFT
        # --------------------------------

        active_users = get_active_for_chat(
            chat_id
        )

        for session in active_users:

            user_id = session[
                "user_id"
            ]

            if user_id not in current_users:

                await self.process_leave(
                    chat_id,
                    user_id
                )


    # ---------------------------------
    # REGISTER CALL
    # ---------------------------------

    async def register_call(
        self,
        chat_id,
        call
    ):

        if not isinstance(
            call,
            types.GroupCall
        ):
            return

        call_id = call.id

        title = await self.get_title(
            chat_id
        )

        self.calls[
            call_id
        ] = {
            "chat_id": chat_id,
            "title": title,
            "call": call
        }

        self.chat_calls[
            chat_id
        ] = call_id

        log.info(
            "VC CALL REGISTERED | chat=%s call=%s",
            chat_id,
            call_id
        )

        # Initial participants
        participants = (
            getattr(
                call,
                "participants",
                []
            )
            or []
        )

        if participants:

            await self.reconcile(
                chat_id,
                call,
                participants,
                {}
            )


    # ---------------------------------
    # DISCOVER GROUP CALL
    # ---------------------------------

    async def discover_call(
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

            # Supergroup / Channel
            if isinstance(
                peer,
                types.InputPeerChannel
            ):

                full = await self.client.invoke(
                    functions.channels.GetFullChannel(
                        channel=peer
                    )
                )

            # Normal group
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

            full_chat = full.full_chat

            group_call = getattr(
                full_chat,
                "call",
                None
            )

            if not group_call:
                return

            # Some Telegram responses return InputGroupCall
            if isinstance(
                group_call,
                types.InputGroupCall
            ):

                call_input = group_call

            elif isinstance(
                group_call,
                types.GroupCall
            ):

                call_input = types.InputGroupCall(
                    id=group_call.id,
                    access_hash=group_call.access_hash
                )

            else:

                return

            result = await self.client.invoke(
                functions.phone.GetGroupCall(
                    call=call_input,
                    limit=100
                )
            )

            call = result.call

            if isinstance(
                call,
                types.GroupCall
            ):

                await self.register_call(
                    chat_id,
                    call
                )

                await self.reconcile(
                    chat_id,
                    call,
                    result.participants,
                    result.users
                )

                log.info(
                    "VC AUTO DISCOVERED | chat=%s",
                    chat_id
                )

        except Exception:

            log.exception(
                "VC discovery failed | chat=%s",
                chat_id
            )


    # ---------------------------------
    # RAW UPDATE
    # ---------------------------------

    async def update(
        self,
        update,
        users=None
    ):

        try:

            log.info(
                "RAW UPDATE RECEIVED: %s",
                type(update).__name__
            )

            # -----------------------------
            # GROUP CALL
            # -----------------------------

            if isinstance(
                update,
                types.UpdateGroupCall
            ):

                chat_id = (
                    -1000000000000
                    - int(update.chat_id)
                )

                call = update.call

                if isinstance(
                    call,
                    types.GroupCall
                ):

                    await self.register_call(
                        chat_id,
                        call
                    )

                elif isinstance(
                    call,
                    types.GroupCallDiscarded
                ):

                    call_id = call.id

                    info = self.calls.pop(
                        call_id,
                        None
                    )

                    self.chat_calls.pop(
                        chat_id,
                        None
                    )

                    if info:

                        active_users = (
                            get_active_for_chat(
                                chat_id
                            )
                        )

                        for session in active_users:

                            await self.process_leave(
                                chat_id,
                                session["user_id"]
                            )

                    log.info(
                        "VC DISCARDED | chat=%s",
                        chat_id
                    )

                return

            # -----------------------------
            # PARTICIPANTS
            # -----------------------------

            if isinstance(
                update,
                types.UpdateGroupCallParticipants
            ):

                call_id = getattr(
                    update.call,
                    "id",
                    None
                )

                if not call_id:

                    return

                info = self.calls.get(
                    call_id
                )

                if not info:

                    log.warning(
                        "Unknown VC call id: %s",
                        call_id
                    )

                    return

                chat_id = info[
                    "chat_id"
                ]

                await self.reconcile(
                    chat_id,
                    info["call"],
                    update.participants,
                    users
                )

        except Exception:

            log.exception(
                "RAW UPDATE ERROR"
            )


    # ---------------------------------
    # POLLING / RECONCILIATION
    # ---------------------------------

    async def poll_once(self):

        # --------------------------------
        # First discover calls
        # --------------------------------

        from database import get_tracked_groups

        groups = get_tracked_groups()

        for group in groups:

            chat_id = group[
                "chat_id"
            ]

            await self.discover_call(
                chat_id
            )

        # --------------------------------
        # Refresh known calls
        # --------------------------------

        for call_id, info in list(
            self.calls.items()
        ):

            try:

                call = info[
                    "call"
                ]

                if not isinstance(
                    call,
                    types.GroupCall
                ):
                    continue

                inp = types.InputGroupCall(
                    id=call.id,
                    access_hash=call.access_hash
                )

                result = await self.client.invoke(
                    functions.phone.GetGroupCall(
                        call=inp,
                        limit=100
                    )
                )

                new_call = result.call

                info[
                    "call"
                ] = new_call

                await self.reconcile(
                    info["chat_id"],
                    new_call,
                    result.participants,
                    result.users
                )

            except Exception as e:

                log.debug(
                    "VC poll error: %s",
                    e
                )


    async def poll(self):

        log.info(
            "VC polling started: %ss",
            self.poll_seconds
        )

        while self.running:

            try:

                await self.poll_once()

            except Exception:

                log.exception(
                    "Polling error"
                )

            await asyncio.sleep(
                self.poll_seconds
            )


    async def stop(self):

        self.running = False
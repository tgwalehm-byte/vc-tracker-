# ============================================
# VC TRACKER
# ============================================

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
    get_tracked_groups,
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

        # call_id -> data
        self.calls = {}

        # chat_id -> call_id
        self.chat_calls = {}

        self.running = True

        self.lock = asyncio.Lock()

    # ========================================
    # TIME
    # ========================================

    @staticmethod
    def now():
        return datetime.now(timezone.utc)

    @staticmethod
    def format_time(dt):

        if not dt:
            return "Unknown"

        return dt.astimezone().strftime(
            "%d-%m-%Y %I:%M:%S %p"
        )

    @staticmethod
    def format_duration(seconds):

        seconds = max(0, int(seconds))

        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)

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

    # ========================================
    # CHAT TITLE
    # ========================================

    async def get_title(self, chat_id):

        try:

            chat = await self.client.get_chat(chat_id)

            return (
                chat.title
                or "Voice Chat"
            )

        except Exception as e:

            log.debug(
                "Unable to get title %s: %s",
                chat_id,
                e
            )

            return "Voice Chat"

    # ========================================
    # USER INFO
    # ========================================

    async def get_user_info(
        self,
        user_id,
        users=None
    ):

        user = None

        # Raw users dictionary
        if users:

            if isinstance(users, dict):

                user = users.get(user_id)

            else:

                for item in users:

                    if getattr(
                        item,
                        "id",
                        None
                    ) == user_id:

                        user = item
                        break

        # Fetch from Telegram if not found
        if user is None:

            try:

                user = await self.client.get_users(
                    user_id
                )

            except Exception as e:

                log.debug(
                    "Unable to get user %s: %s",
                    user_id,
                    e
                )

        if user is None:

            return (
                "Unknown User",
                None
            )

        first_name = (
            getattr(
                user,
                "first_name",
                None
            )
            or ""
        )

        last_name = (
            getattr(
                user,
                "last_name",
                None
            )
            or ""
        )

        name = (
            f"{first_name} {last_name}"
        ).strip()

        if not name:
            name = "Unknown User"

        username = getattr(
            user,
            "username",
            None
        )

        return (
            name,
            username
        )

    # ========================================
    # JOIN LOG
    # ========================================

    async def join_log(self, data):

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

        await self.send_log(text)

    # ========================================
    # LEFT LOG
    # ========================================

    async def leave_log(self, data):

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

        await self.send_log(text)

    # ========================================
    # GET USER ID FROM PEER
    # ========================================

    @staticmethod
    def get_user_id(peer):

        if isinstance(
            peer,
            types.PeerUser
        ):
            return peer.user_id

        return None

    # ========================================
    # START USER SESSION
    # ========================================

    async def process_join(
        self,
        chat_id,
        user_id,
        join_time=None,
        users=None,
        title=None
    ):

        # Group must be tracked
        if not is_tracked(chat_id):
            return

        # Already active
        if get_active(
            user_id,
            chat_id
        ):
            return

        # User information
        name, username = await self.get_user_info(
            user_id,
            users
        )

        # Join time
        if join_time is None:

            join_time = self.now()

        # Group title
        if title is None:

            title = await self.get_title(
                chat_id
            )

        # Save active session
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

        if not data:
            return

        # Send JOIN message
        await self.join_log(data)

        log.info(
            "VC JOIN | user=%s | chat=%s",
            user_id,
            chat_id
        )

    # ========================================
    # END USER SESSION
    # ========================================

    async def process_leave(
        self,
        chat_id,
        user_id
    ):

        if not is_tracked(chat_id):
            return

        # Check active session
        if not get_active(
            user_id,
            chat_id
        ):
            return

        leave_time = self.now()

        finished = finish_session(
            user_id,
            chat_id,
            leave_time
        )

        if not finished:
            return

        # Send LEFT message
        await self.leave_log(
            finished
        )

        log.info(
            "VC LEFT | user=%s | chat=%s | duration=%s",
            user_id,
            chat_id,
            finished["duration_seconds"]
        )

    # ========================================
    # REGISTER GROUP CALL
    # ========================================

    async def register_call(
        self,
        chat_id,
        call,
        users=None
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

        self.calls[call_id] = {
            "chat_id": chat_id,
            "title": title,
            "call": call,
        }

        self.chat_calls[chat_id] = call_id

        log.info(
            "VC CALL REGISTERED | chat=%s | call=%s",
            chat_id,
            call_id
        )

        participants = (
            getattr(
                call,
                "participants",
                None
            )
            or []
        )

        if participants:

            await self.reconcile(
                chat_id,
                call,
                participants,
                users or {}
            )

    # ========================================
    # RECONCILE PARTICIPANTS
    # ========================================

    async def reconcile(
        self,
        chat_id,
        call,
        participants,
        users=None
    ):

        if not is_tracked(chat_id):
            return

        info = self.calls.get(
            call.id,
            {}
        )

        title = info.get(
            "title"
        )

        if not title:

            title = await self.get_title(
                chat_id
            )

        current_users = set()

        # -------------------------------
        # Process Telegram participants
        # -------------------------------

        for participant in (
            participants or []
        ):

            user_id = self.get_user_id(
                getattr(
                    participant,
                    "peer",
                    None
                )
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

            # Explicit LEFT
            if left:

                await self.process_leave(
                    chat_id,
                    user_id
                )

                continue

            current_users.add(
                user_id
            )

            # Telegram participant date
            timestamp = getattr(
                participant,
                "date",
                None
            )

            join_time = None

            if timestamp:

                try:

                    join_time = datetime.fromtimestamp(
                        timestamp,
                        timezone.utc
                    )

                except Exception:

                    join_time = None

            # New user
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
        # Detect users missing from FULL
        # participant list
        # --------------------------------

        active_sessions = get_active_for_chat(
            chat_id
        )

        for session in active_sessions:

            user_id = session[
                "user_id"
            ]

            if user_id not in current_users:

                await self.process_leave(
                    chat_id,
                    user_id
                )

    # ========================================
    # BUILD INPUT GROUP CALL
    # ========================================

    @staticmethod
    def make_input_call(call):

        if isinstance(
            call,
            types.InputGroupCall
        ):
            return call

        if isinstance(
            call,
            types.GroupCall
        ):

            return types.InputGroupCall(
                id=call.id,
                access_hash=call.access_hash
            )

        return None

    # ========================================
    # FETCH CURRENT VC
    # ========================================

    async def fetch_current_call(
        self,
        chat_id
    ):

        try:

            peer = await self.client.resolve_peer(
                chat_id
            )

        except Exception as e:

            log.error(
                "resolve_peer failed | chat=%s | %s",
                chat_id,
                e
            )

            return None

        try:

            # -----------------------------
            # SUPERGROUP / CHANNEL
            # -----------------------------

            if isinstance(
                peer,
                types.InputPeerChannel
            ):

                result = await self.client.invoke(
                    functions.channels.GetFullChannel(
                        channel=peer
                    )
                )

            # -----------------------------
            # NORMAL GROUP
            # -----------------------------

            elif isinstance(
                peer,
                types.InputPeerChat
            ):

                result = await self.client.invoke(
                    functions.messages.GetFullChat(
                        chat_id=peer.chat_id
                    )
                )

            else:

                log.warning(
                    "Unsupported peer type: %s",
                    type(peer).__name__
                )

                return None

        except Exception as e:

            log.error(
                "Unable to get full chat | chat=%s | %s",
                chat_id,
                e
            )

            return None

        full_chat = getattr(
            result,
            "full_chat",
            None
        )

        if not full_chat:
            return None

        group_call = getattr(
            full_chat,
            "call",
            None
        )

        if not group_call:
            return None

        return group_call

    # ========================================
    # DISCOVER ACTIVE VC
    # ========================================

    async def discover_call(
        self,
        chat_id
    ):

        if not is_tracked(chat_id):
            return

        group_call = await self.fetch_current_call(
            chat_id
        )

        if not group_call:
            return

        call_input = self.make_input_call(
            group_call
        )

        if not call_input:
            return

        try:

            result = await self.client.invoke(
                functions.phone.GetGroupCall(
                    call=call_input,
                    limit=100
                )
            )

        except Exception as e:

            log.error(
                "GetGroupCall failed | chat=%s | %s",
                chat_id,
                e
            )

            return

        call = getattr(
            result,
            "call",
            None
        )

        if not isinstance(
            call,
            types.GroupCall
        ):
            return

        # Save call
        await self.register_call(
            chat_id,
            call,
            getattr(
                result,
                "users",
                {}
            )
        )

        # Full reconciliation
        await self.reconcile(
            chat_id,
            call,
            getattr(
                result,
                "participants",
                []
            ),
            getattr(
                result,
                "users",
                {}
            )
        )

        log.info(
            "VC AUTO DISCOVERED | chat=%s | call=%s",
            chat_id,
            call.id
        )

    # ========================================
    # REFRESH KNOWN VC
    # ========================================

    async def refresh_call(
        self,
        call_id,
        info
    ):

        chat_id = info[
            "chat_id"
        ]

        old_call = info[
            "call"
        ]

        call_input = self.make_input_call(
            old_call
        )

        if not call_input:
            return

        try:

            result = await self.client.invoke(
                functions.phone.GetGroupCall(
                    call=call_input,
                    limit=100
                )
            )

        except Exception as e:

            log.debug(
                "Refresh VC failed | call=%s | %s",
                call_id,
                e
            )

            return

        call = getattr(
            result,
            "call",
            None
        )

        # VC no longer available
        if not isinstance(
            call,
            types.GroupCall
        ):

            await self.close_call(
                call_id,
                chat_id
            )

            return

        info["call"] = call

        participants = getattr(
            result,
            "participants",
            []
        )

        users = getattr(
            result,
            "users",
            {}
        )

        await self.reconcile(
            chat_id,
            call,
            participants,
            users
        )

    # ========================================
    # CLOSE VC
    # ========================================

    async def close_call(
        self,
        call_id,
        chat_id
    ):

        self.calls.pop(
            call_id,
            None
        )

        if self.chat_calls.get(
            chat_id
        ) == call_id:

            self.chat_calls.pop(
                chat_id,
                None
            )

        # Close every active session
        active_sessions = get_active_for_chat(
            chat_id
        )

        for session in active_sessions:

            await self.process_leave(
                chat_id,
                session["user_id"]
            )

        log.info(
            "VC CLOSED | chat=%s | call=%s",
            chat_id,
            call_id
        )

    # ========================================
    # RAW UPDATE
    # ========================================

    async def update(
        self,
        update,
        users=None,
        chats=None
    ):

        try:

            update_name = type(
                update
            ).__name__

            log.info(
                "RAW UPDATE: %s",
                update_name
            )

            # =================================
            # GROUP CALL UPDATE
            # =================================

            if isinstance(
                update,
                types.UpdateGroupCall
            ):

                # IMPORTANT:
                # Do NOT manually convert raw ID
                # like -1000000000000 - id.
                #
                # Resolve group from known calls/tracked
                # groups instead.

                call = update.call

                # Find existing call by call ID
                call_id = getattr(
                    call,
                    "id",
                    None
                )

                known = None

                if call_id:

                    known = self.calls.get(
                        call_id
                    )

                if isinstance(
                    call,
                    types.GroupCall
                ):

                    if known:

                        chat_id = known[
                            "chat_id"
                        ]

                        await self.register_call(
                            chat_id,
                            call
                        )

                    else:

                        # Try all tracked groups.
                        # This avoids dangerous raw ID conversion.
                        groups = get_tracked_groups()

                        for group in groups:

                            chat_id = group[
                                "chat_id"
                            ]

                            try:

                                current = (
                                    await self.fetch_current_call(
                                        chat_id
                                    )
                                )

                                current_input = (
                                    self.make_input_call(
                                        current
                                    )
                                )

                                if (
                                    current_input
                                    and
                                    getattr(
                                        current_input,
                                        "id",
                                        None
                                    ) == call_id
                                ):

                                    await self.register_call(
                                        chat_id,
                                        call
                                    )

                                    break

                            except Exception:

                                continue

                elif isinstance(
                    call,
                    types.GroupCallDiscarded
                ):

                    if known:

                        await self.close_call(
                            call_id,
                            known["chat_id"]
                        )

                return

            # =================================
            # PARTICIPANT UPDATE
            # =================================

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

                # Unknown call:
                # discover it from tracked groups
                if not info:

                    groups = get_tracked_groups()

                    for group in groups:

                        chat_id = group[
                            "chat_id"
                        ]

                        if self.chat_calls.get(
                            chat_id
                        ) == call_id:

                            info = self.calls.get(
                                call_id
                            )

                            break

                if not info:

                    log.debug(
                        "Unknown VC call: %s",
                        call_id
                    )

                    return

                chat_id = info[
                    "chat_id"
                ]

                # IMPORTANT:
                # Participant update can be a DELTA.
                #
                # Therefore we process explicit joins/leaves
                # here, but the full reconciliation happens
                # in polling.

                participant_list = (
                    getattr(
                        update,
                        "participants",
                        []
                    )
                    or []
                )

                for participant in participant_list:

                    user_id = self.get_user_id(
                        getattr(
                            participant,
                            "peer",
                            None
                        )
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

                    else:

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

                                pass

                        await self.process_join(
                            chat_id=chat_id,
                            user_id=user_id,
                            join_time=join_time,
                            users=users,
                            title=info.get(
                                "title"
                            )
                        )

                return

        except Exception:

            log.exception(
                "RAW UPDATE ERROR"
            )

    # ========================================
    # POLL ONCE
    # ========================================

    async def poll_once(self):

        groups = get_tracked_groups()

        # =================================
        # AUTO DISCOVERY
        # =================================

        for group in groups:

            chat_id = group[
                "chat_id"
            ]

            try:

                await self.discover_call(
                    chat_id
                )

            except Exception:

                log.exception(
                    "Discovery error | chat=%s",
                    chat_id
                )

        # =================================
        # REFRESH KNOWN CALLS
        # =================================

        for call_id, info in list(
            self.calls.items()
        ):

            try:

                await self.refresh_call(
                    call_id,
                    info
                )

            except Exception:

                log.exception(
                    "Refresh error | call=%s",
                    call_id
                )

    # ========================================
    # BACKGROUND POLLER
    # ========================================

    async def poll(self):

        log.info(
            "VC POLLER STARTED | every %ss",
            self.poll_seconds
        )

        while self.running:

            try:

                await self.poll_once()

            except asyncio.CancelledError:

                break

            except Exception:

                log.exception(
                    "VC POLLER ERROR"
                )

            try:

                await asyncio.sleep(
                    self.poll_seconds
                )

            except asyncio.CancelledError:

                break

    # ========================================
    # STOP
    # ========================================

    async def stop(self):

        self.running = False

        log.info(
            "VC TRACKER STOPPED"
        )
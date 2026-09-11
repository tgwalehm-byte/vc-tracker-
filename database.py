from pymongo import MongoClient, ASCENDING, DESCENDING

from config import MONGO_URL


mongo = MongoClient(
    MONGO_URL,
    serverSelectionTimeoutMS=10000
)

db = mongo["vc_tracker"]

sessions = db["sessions"]
active = db["active_sessions"]
tracked = db["tracked_groups"]


# -----------------------------
# INDEXES
# -----------------------------

sessions.create_index([
    ("user_id", ASCENDING),
    ("chat_id", ASCENDING),
    ("join_time", DESCENDING)
])

sessions.create_index([
    ("chat_id", ASCENDING),
    ("join_time", DESCENDING)
])

active.create_index([
    ("user_id", ASCENDING),
    ("chat_id", ASCENDING)
], unique=True)

active.create_index([
    ("chat_id", ASCENDING)
])

tracked.create_index(
    [("chat_id", ASCENDING)],
    unique=True
)


# -----------------------------
# TRACKED GROUPS
# -----------------------------

def add_tracked_group(
    chat_id,
    title,
    added_by
):
    tracked.update_one(
        {"chat_id": chat_id},
        {
            "$set": {
                "chat_id": chat_id,
                "title": title,
                "added_by": added_by
            }
        },
        upsert=True
    )


def remove_tracked_group(chat_id):

    result = tracked.delete_one({
        "chat_id": chat_id
    })

    return result.deleted_count > 0


def is_tracked(chat_id):

    return tracked.find_one({
        "chat_id": chat_id
    }) is not None


def get_tracked_groups():

    return list(
        tracked.find({}).sort(
            "title",
            ASCENDING
        )
    )


# -----------------------------
# ACTIVE SESSION
# -----------------------------

def start_session(
    user_id,
    name,
    username,
    chat_id,
    chat_title,
    join_time
):

    active.update_one(
        {
            "user_id": user_id,
            "chat_id": chat_id
        },
        {
            "$setOnInsert": {
                "user_id": user_id,
                "name": name,
                "username": username,
                "chat_id": chat_id,
                "chat_title": chat_title,
                "join_time": join_time
            }
        },
        upsert=True
    )


def get_active(
    user_id,
    chat_id
):

    return active.find_one({
        "user_id": user_id,
        "chat_id": chat_id
    })


def get_active_for_chat(chat_id):

    return list(
        active.find({
            "chat_id": chat_id
        })
    )


def finish_session(
    user_id,
    chat_id,
    leave_time
):

    data = active.find_one_and_delete({
        "user_id": user_id,
        "chat_id": chat_id
    })

    if not data:
        return None

    data.pop("_id", None)

    join_time = data["join_time"]

    duration = max(
        0,
        int(
            (
                leave_time - join_time
            ).total_seconds()
        )
    )

    data["leave_time"] = leave_time
    data["duration_seconds"] = duration

    sessions.insert_one(data)

    return data


# -----------------------------
# REPORT
# -----------------------------

def get_stats(
    user_id,
    chat_id,
    since
):

    rows = list(
        sessions.find({
            "user_id": user_id,
            "chat_id": chat_id,
            "join_time": {
                "$gte": since
            }
        })
    )

    joined = len(rows)

    left = len(rows)

    total = sum(
        int(
            row.get(
                "duration_seconds",
                0
            )
        )
        for row in rows
    )

    return {
        "joined": joined,
        "left": left,
        "total": total
    }


def get_history(
    user_id,
    chat_id,
    limit=10
):

    return list(
        sessions.find({
            "user_id": user_id,
            "chat_id": chat_id
        })
        .sort(
            "join_time",
            DESCENDING
        )
        .limit(limit)
    )
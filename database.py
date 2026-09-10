from pymongo import MongoClient, ASCENDING, DESCENDING

from config import MONGO_URL


# ==========================================
# MONGODB
# ==========================================

mongo = MongoClient(
    MONGO_URL,
    serverSelectionTimeoutMS=10000
)

db = mongo["vc_tracker"]


# ==========================================
# COLLECTIONS
# ==========================================

sessions = db["sessions"]

active_sessions = db["active_sessions"]

tracked_groups = db["tracked_groups"]


# ==========================================
# INDEXES
# ==========================================

sessions.create_index([
    ("chat_id", ASCENDING),
    ("user_id", ASCENDING),
    ("join_time", DESCENDING)
])

sessions.create_index([
    ("user_id", ASCENDING),
    ("join_time", DESCENDING)
])

active_sessions.create_index(
    [
        ("chat_id", ASCENDING),
        ("user_id", ASCENDING)
    ],
    unique=True
)

tracked_groups.create_index(
    [
        ("chat_id", ASCENDING)
    ],
    unique=True
)


# ==========================================
# TRACKED GROUPS
# ==========================================

def add_tracked_group(
    chat_id,
    title,
    added_by
):

    tracked_groups.update_one(
        {
            "chat_id": chat_id
        },
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

    result = tracked_groups.delete_one(
        {
            "chat_id": chat_id
        }
    )

    return result.deleted_count > 0


def is_tracked(chat_id):

    return (
        tracked_groups.find_one(
            {
                "chat_id": chat_id
            }
        )
        is not None
    )


def get_tracked_groups():

    return list(
        tracked_groups.find({}).sort(
            "title",
            ASCENDING
        )
    )


# ==========================================
# ACTIVE SESSION
# ==========================================

def start_session(
    user_id,
    name,
    username,
    chat_id,
    chat_title,
    join_time
):

    active_sessions.update_one(
        {
            "chat_id": chat_id,
            "user_id": user_id
        },
        {
            "$set": {
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

    return active_sessions.find_one(
        {
            "chat_id": chat_id,
            "user_id": user_id
        }
    )


def get_active_for_chat(chat_id):

    return list(
        active_sessions.find(
            {
                "chat_id": chat_id
            }
        )
    )


def end_session(
    user_id,
    chat_id,
    leave_time
):

    session = get_active(
        user_id,
        chat_id
    )

    if not session:
        return None


    join_time = session["join_time"]


    duration = max(
        0,
        int(
            (
                leave_time - join_time
            ).total_seconds()
        )
    )


    finished = {
        "user_id": session["user_id"],
        "name": session["name"],
        "username": session.get("username"),
        "chat_id": session["chat_id"],
        "chat_title": session["chat_title"],
        "join_time": join_time,
        "leave_time": leave_time,
        "duration_seconds": duration
    }


    sessions.insert_one(
        finished
    )


    active_sessions.delete_one(
        {
            "_id": session["_id"]
        }
    )


    return finished
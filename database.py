from pymongo import MongoClient, ASCENDING, DESCENDING
from config import MONGO_URL

mongo = MongoClient(
    MONGO_URL,
    serverSelectionTimeoutMS=10000
)

db = mongo["vc_tracker"]

sessions = db["sessions"]
active_sessions = db["active_sessions"]

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


def get_active(user_id, chat_id):
    return active_sessions.find_one({
        "chat_id": chat_id,
        "user_id": user_id
    })


def end_session(user_id, chat_id, leave_time):
    session = get_active(user_id, chat_id)

    if not session:
        return None

    join_time = session["join_time"]

    duration = int(
        (leave_time - join_time).total_seconds()
    )

    finished = {
        "user_id": session["user_id"],
        "name": session["name"],
        "username": session.get("username"),
        "chat_id": session["chat_id"],
        "chat_title": session["chat_title"],
        "join_time": join_time,
        "leave_time": leave_time,
        "duration_seconds": max(0, duration)
    }

    sessions.insert_one(finished)

    active_sessions.delete_one({
        "_id": session["_id"]
    })

    return finished


def get_history(user_id, chat_id=None, limit=20):
    query = {
        "user_id": user_id
    }

    if chat_id is not None:
        query["chat_id"] = chat_id

    return list(
        sessions.find(query)
        .sort("join_time", DESCENDING)
        .limit(limit)
    )


def get_count(user_id, start_time, chat_id=None):
    query = {
        "user_id": user_id,
        "join_time": {
            "$gte": start_time
        }
    }

    if chat_id is not None:
        query["chat_id"] = chat_id

    return sessions.count_documents(query)


def get_total_seconds(user_id, start_time, chat_id=None):
    query = {
        "user_id": user_id,
        "join_time": {
            "$gte": start_time
        }
    }

    if chat_id is not None:
        query["chat_id"] = chat_id

    total = 0

    for item in sessions.find(
        query,
        {"duration_seconds": 1}
    ):
        total += int(
            item.get("duration_seconds", 0)
        )

    return total
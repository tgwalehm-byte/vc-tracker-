from datetime import datetime, timezone, timedelta
from pymongo import MongoClient, ASCENDING, DESCENDING

from config import MONGO_URL

mongo = MongoClient(
    MONGO_URL,
    serverSelectionTimeoutMS=10000
)

db = mongo["vc_tracker"]

sessions = db["sessions"]
active_sessions = db["active_sessions"]
tracked_groups = db["tracked_groups"]

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
    [("chat_id", ASCENDING), ("user_id", ASCENDING)],
    unique=True
)

tracked_groups.create_index(
    [("chat_id", ASCENDING)],
    unique=True
)


def add_tracked_group(chat_id, title, added_by):
    tracked_groups.update_one(
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
    result = tracked_groups.delete_one({"chat_id": chat_id})
    return result.deleted_count > 0


def is_tracked(chat_id):
    return tracked_groups.find_one({"chat_id": chat_id}) is not None


def get_tracked_groups():
    return list(tracked_groups.find({}).sort("title", ASCENDING))


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


def get_active_for_chat(chat_id):
    return list(active_sessions.find({"chat_id": chat_id}))


def end_session(user_id, chat_id, leave_time):
    session = get_active(user_id, chat_id)

    if not session:
        return None

    join_time = session["join_time"]

    duration = max(
        0,
        int((leave_time - join_time).total_seconds())
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

    sessions.insert_one(finished)

    active_sessions.delete_one({
        "_id": session["_id"]
    })

    return finished


def get_user_report(user_id, chat_id):
    now = datetime.now(timezone.utc)

    day_start = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    week_start = day_start - timedelta(
        days=day_start.weekday()
    )

    month_start = day_start.replace(day=1)

    def stats(start):
        data = list(
            sessions.find({
                "user_id": user_id,
                "chat_id": chat_id,
                "join_time": {
                    "$gte": start,
                    "$lte": now
                }
            })
        )

        joined = len(data)
        left = len(data)

        total_seconds = sum(
            int(x.get("duration_seconds", 0))
            for x in data
        )

        return joined, left, total_seconds

    today = stats(day_start)
    week = stats(week_start)
    month = stats(month_start)

    return {
        "today": today,
        "week": week,
        "month": month
    }


def get_recent_sessions(user_id, chat_id, limit=10):
    return list(
        sessions.find({
            "user_id": user_id,
            "chat_id": chat_id
        })
        .sort("join_time", DESCENDING)
        .limit(limit)
    )
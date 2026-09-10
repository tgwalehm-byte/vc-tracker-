import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

BOT_TOKEN = os.environ["BOT_TOKEN"]
SESSION_STRING = os.environ["SESSION_STRING"]

MONGO_URL = os.environ["MONGO_URL"]
LOG_CHANNEL = int(os.environ["LOG_CHANNEL"])

OWNER_ID = int(os.environ["OWNER_ID"])

POLL_SECONDS = int(
    os.getenv("POLL_SECONDS", "3")
)
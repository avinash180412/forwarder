#!/usr/bin/env python3
"""
High-speed OSINT bridge using Telegram user account (Telethon).

Features:
- Multi-command parallel handling
- Per-command async tracking
- Event-based (no polling)
- Ignores processing/searching messages
- Returns only final OSINT data
"""

import asyncio
import os
import time
from datetime import datetime
import threading
from dotenv import load_dotenv
from telethon import TelegramClient, events
from flask import Flask

# ================= CONFIG =================
load_dotenv()

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SESSION = os.getenv("TG_SESSION", "stark_bridge.session")

SOURCE_GROUP_A = os.getenv("SOURCE_GROUP_A", "@YourSourceGroupA")
TARGET_GROUP_B = os.getenv("TARGET_GROUP_B", "@YourStarkGroup")

WAIT_SECONDS = float(os.getenv("WAIT_SECONDS", "15"))

COMMANDS = {
    "num": "Mobile Number Search",
    "num2": "Power Mobile Search",
    "aadh": "Aadhaar V2 Search",
    "rashan": "Rashan Card Details",
    "upi": "UPI Information",
    "icmr": "ICMR Database",
    "vehicle": "Vehicle RC Information",
    "tguser": "Telegram User Info",
    "gst": "GST Number Lookup",
    "ifsc": "IFSC Code Lookup",
}

# =========================================

client = TelegramClient(SESSION, API_ID, API_HASH)
TARGET_GROUP_ENTITY = None

# sent_msg_id -> tracking info
pending_requests = {}

# ---------- FILTERS ----------
IGNORE_KEYWORDS = [
    "searching",
    "processing",
    "extracting",
    "please wait",
    "Database",
    "searching mobile database...",
    "searching upi database...,"
    
]

FINAL_HINT_KEYWORDS = [
    "{", "name", "mobile", "address",
    "upi", "pan", "dob", "vehicle", "ifsc","gst","rashan","username","telegram",
    "boombing",
]

def is_final_reply(text: str) -> bool:
    lower = text.lower()
    if any(k in lower for k in IGNORE_KEYWORDS):
        return False
    return any(k in text for k in FINAL_HINT_KEYWORDS)

# ---------- SEND COMMAND ----------
async def send_command_to_stark(cmd, value, source_chat, source_msg_id):
    msg = await client.send_message(
        TARGET_GROUP_ENTITY,
        f"/{cmd} {value}".strip()
    )

    future = asyncio.get_running_loop().create_future()

    pending_requests[msg.id] = {
        "future": future,
        "source_chat": source_chat,
        "source_msg_id": source_msg_id,
        "timestamp": time.time(),
    }

    return future

# ---------- HANDLE STARK REPLIES ----------
@client.on(events.NewMessage(chats=TARGET_GROUP_B))
async def handle_stark_reply(event):
    msg = event.message
    reply_id = getattr(msg, "reply_to_msg_id", None)
    if not reply_id:
        return

    if reply_id not in pending_requests:
        return

    text = (msg.text or msg.message or "").strip()
    if not text:
        return

    if not is_final_reply(text):
        return

    data = pending_requests.pop(reply_id)
    future = data["future"]

    if not future.done():
        future.set_result(text)

# ---------- GROUP A COMMAND HANDLER ----------
@client.on(events.NewMessage(chats=SOURCE_GROUP_A))
async def handle_group_a_message(event):
    text = (event.raw_text or "").strip()
    if not text.startswith("/"):
        return

    parts = text.split(maxsplit=1)
    cmd = parts[0][1:].lower()
    value = parts[1] if len(parts) > 1 else ""

    if cmd not in COMMANDS:
        return

    print(f"[Group A] /{cmd} {value}")

    future = await send_command_to_stark(
        cmd,
        value,
        event.chat_id,
        event.message.id
    )

    try:
        result = await asyncio.wait_for(future, timeout=WAIT_SECONDS)

        await client.send_message(
            entity=event.chat_id,
            message=result,
            reply_to=event.message.id,
        )

    except asyncio.TimeoutError:
        await client.send_message(
            entity=event.chat_id,
            message="❌ No final response received from SHADOW OSINT NETWORK.",
            reply_to=event.message.id,
        )

# ---------- CLEANUP TASK ----------
async def cleanup_expired_requests():
    while True:
        now = time.time()
        expired = [
            k for k, v in pending_requests.items()
            if now - v["timestamp"] > WAIT_SECONDS
        ]
        for k in expired:
            pending_requests.pop(k, None)
        await asyncio.sleep(5)

# ---------- MAIN ----------
async def main():
    global TARGET_GROUP_ENTITY

    print("Connecting Telegram client...")
    await client.start()
    me = await client.get_me()
    print(f"Logged in as {me.first_name} ({me.id})")

    TARGET_GROUP_ENTITY = await client.get_entity(TARGET_GROUP_B)
    print("Target Stark group resolved.")

    asyncio.create_task(cleanup_expired_requests())

    print("Bridge is running...")
    await client.run_until_disconnected()

# ---------- KEEP ALIVE (RENDER) ----------
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "Telegram OSINT Bridge is running."

def run_web():
    web_app.run(host="0.0.0.0", port=10000)

# ---------- ENTRY ----------
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    with client:
        client.loop.run_until_complete(main())

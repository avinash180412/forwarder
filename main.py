#!/usr/bin/env python3
"""
Single-phase OSINT bridge using your user account (no bot).

Flow:
- Listen to SOURCE_GROUP_A for commands like /num 9999999999, /vehicle XX00YY1234, etc.
- When a supported command is seen:
    - Send the same command to TARGET_GROUP_B (Stark OSINT group).
    - Wait WAIT_SECONDS.
    - Find the reply in TARGET_GROUP_B that replies to that message.
    - Send that reply back to SOURCE_GROUP_A as your account,
      replying to the original command message.

No Bot API is used, only Telegram API via Telethon with your own account.
"""

import asyncio
import os
import time
from datetime import datetime

from dotenv import load_dotenv
from telethon import TelegramClient, events

# ----------------- CONFIG -----------------
load_dotenv()

API_ID = int(os.getenv("TG_API_ID") or 0)
API_HASH = os.getenv("TG_API_HASH") or ""
SESSION = os.getenv("TG_SESSION") or "stark_bridge.session"

# Group where commands are written (Group A)
SOURCE_GROUP_A = os.getenv("SOURCE_GROUP_A") or "@YourSourceGroupA"

# Stark OSINT group (Group B)
TARGET_GROUP_B = os.getenv("TARGET_GROUP_B") or "@YourStarkGroup"

# How long to wait (in seconds) for a reply from Stark group
WAIT_SECONDS = float(os.getenv("WAIT_SECONDS") or 7.0)

# Supported commands (same style as your Stark network)
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

client = TelegramClient(SESSION, API_ID, API_HASH)
TARGET_GROUP_ENTITY = None  # set in main()
# ------------------------------------------


async def send_to_stark_and_get_reply(command: str, value: str) -> str | None:
    """
    Sends '/command value' to Stark group and returns the first reply
    that replies to that message. Returns None if not found in time.
    """
    global TARGET_GROUP_ENTITY

    msg_text = f"/{command} {value}".strip()
    sent = await client.send_message(TARGET_GROUP_ENTITY, msg_text)
    sent_id = sent.id

    # Wait some time for the bot to reply
    await asyncio.sleep(WAIT_SECONDS)

    # Fetch recent messages in Stark group, find reply to our command
    msgs = await client.get_messages(TARGET_GROUP_ENTITY, limit=30)
    for m in msgs:
        if getattr(m, "reply_to_msg_id", None) == sent_id:
            return m.text or m.message

    return None


@client.on(events.NewMessage(chats=SOURCE_GROUP_A))
async def handle_group_a_message(event: events.NewMessage.Event):
    """
    Triggered when a new message appears in Group A.
    If it looks like a supported command, send to Stark group and pipe reply back.
    """
    text = (event.raw_text or "").strip()
    if not text.startswith("/"):
        return  # not a command

    parts = text.split(maxsplit=2)
    if not parts:
        return

    cmd = parts[0].lstrip("/").lower()
    if cmd not in COMMANDS:
        return  # not one of our OSINT commands

    # Extract value after the command
    value = ""
    if len(parts) >= 2:
        value = parts[1].strip()
        # If you need to support spaces in the value, use:
        # value = " ".join(parts[1:]).strip()

    query_msg = event.message
    query_msg_id = query_msg.id
    query_chat_id = query_msg.chat_id

    print(f"\n[Group A] Detected command: /{cmd} {value} (msg_id={query_msg_id})")

    # Send to Stark and get reply
    reply = await send_to_stark_and_get_reply(cmd, value)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if reply:
        print(f"[{timestamp}] Reply received from Stark. Sending back to Group A...")
        # Send back to Group A, replying to original command message
        await client.send_message(
            entity=query_chat_id,
            message=reply,
            reply_to=query_msg_id,
        )
    else:
        print(f"[{timestamp}] No reply found in Stark within {WAIT_SECONDS} seconds.")
        # Optionally notify in Group A that no reply was found:
        # await client.send_message(
        #     entity=query_chat_id,
        #     message=f"No reply from Stark within {WAIT_SECONDS} seconds.",
        #     reply_to=query_msg_id,
        # )


async def main():
    global TARGET_GROUP_ENTITY

    print("Connecting as user account...")
    await client.start()
    me = await client.get_me()
    print(f"Logged in as: {me.id} - {me.first_name}")

    # Resolve Stark group entity once
    TARGET_GROUP_ENTITY = await client.get_entity(TARGET_GROUP_B)
    print("Stark group resolved as:", TARGET_GROUP_ENTITY)

    print(f"\nListening in SOURCE_GROUP_A = {SOURCE_GROUP_A}")
    print("Send commands like /num 9999999999 in that group.\n")

    await client.run_until_disconnected()
# ---------- Keep Render Web Service Alive ----------
from flask import Flask
import threading

web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "Telegram OSINT Bridge is running."

def run_web():
    web_app.run(host="0.0.0.0", port=10000)
# ---------------------------------------------------



if __name__ == "__main__":
    # Start Flask server in background thread
    threading.Thread(target=run_web, daemon=True).start()

    try:
        with client:
            client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")


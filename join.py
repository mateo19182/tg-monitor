#!/usr/bin/env python3
"""Preview and join private groups/channels via invite links, and find channels' linked discussion groups.

  python join.py preview https://t.me/+8qAC-YJC3y04NGEy ...   # title/size/approval-needed, no join
  python join.py join https://t.me/+8qAC-YJC3y04NGEy          # join (or send join request)
  python join.py linked RybarESP infodefSPAIN                   # show each channel's discussion group
  python join.py joinlinked RybarESP                            # join a channel's discussion group

Safe to run while collect.py is running: it opens the session read-only and connects with an
in-memory copy, so the session file is never locked by two processes.
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, functions
from telethon.errors import InviteRequestSentError, UserAlreadyParticipantError
from telethon.sessions import SQLiteSession, StringSession
from telethon.tl.types import ChatInviteAlready, PeerChannel

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]


def client() -> TelegramClient:
    s = StringSession(StringSession.save(SQLiteSession(str(HERE / "tgmon"))))
    return TelegramClient(s, API_ID, API_HASH)


def invite_hash(link: str) -> str:
    return link.rstrip("/").split("/")[-1].lstrip("+").replace("joinchat/", "")


async def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        return
    cmd, args = sys.argv[1], sys.argv[2:]
    c = client()
    await c.connect()
    try:
        if cmd == "preview":
            for link in args:
                try:
                    r = await c(functions.messages.CheckChatInviteRequest(invite_hash(link)))
                except Exception as e:  # noqa: BLE001  expired/invalid hashes are common
                    print(f"{link}\t{type(e).__name__}")
                    await asyncio.sleep(1)
                    continue
                if isinstance(r, ChatInviteAlready):
                    print(f"{link}\talready a member: {r.chat.title} id={r.chat.id}")
                else:
                    kind = "channel" if r.broadcast else ("megagroup" if r.megagroup else "group")
                    print(f"{link}\t{r.title}\t{kind}\tmembers={r.participants_count}\trequest_needed={r.request_needed}")
                await asyncio.sleep(1)
        elif cmd == "join":
            for link in args:
                try:
                    r = await c(functions.messages.ImportChatInviteRequest(invite_hash(link)))
                    chat = r.chats[0]
                    print(f"joined {chat.title} id={chat.id}  -> add to channels.csv as: {chat.id}")
                except InviteRequestSentError:
                    print(f"{link}: join request sent, awaiting admin approval")
                except UserAlreadyParticipantError:
                    print(f"{link}: already a member")
                await asyncio.sleep(3)
        elif cmd in ("linked", "joinlinked"):
            for handle in args:
                ent = await c.get_entity(handle)
                full = await c(functions.channels.GetFullChannelRequest(ent))
                lid = full.full_chat.linked_chat_id
                if not lid:
                    print(f"{handle}: no linked discussion group")
                    continue
                try:
                    g = await c.get_entity(PeerChannel(lid))
                    print(f"{handle}: linked group '{g.title}' @{g.username} id={g.id} members={getattr(g, 'participants_count', '?')}")
                    if cmd == "joinlinked":
                        await c(functions.channels.JoinChannelRequest(g))
                        print(f"  joined -> add to channels.csv as: {g.username or g.id}")
                except Exception as e:  # noqa: BLE001
                    print(f"{handle}: linked group id={lid} not accessible ({e})")
                await asyncio.sleep(1)
        else:
            print(__doc__)
    finally:
        await c.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Non-interactive two-step Telegram login (so it can be driven from a non-TTY session).

  python login.py send +34XXXXXXXXX      # Telegram sends a code to your app/SMS
  python login.py code 12345             # finish sign-in with the code
  python login.py password 'your2fa'     # only if the account has 2FA enabled
  python login.py check                  # show who is logged in
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION = str(HERE / "tgmon")
STATE = HERE / ".login_state.json"


async def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    try:
        if cmd == "check":
            if await client.is_user_authorized():
                me = await client.get_me()
                print(f"logged in as {me.first_name} (@{me.username}) id={me.id}")
            else:
                print("not logged in")
        elif cmd == "send":
            phone = sys.argv[2]
            sent = await client.send_code_request(phone)
            STATE.write_text(json.dumps({"phone": phone, "hash": sent.phone_code_hash}))
            os.chmod(STATE, 0o600)
            print("code sent; now run: python login.py code <code>")
        elif cmd == "code":
            st = json.loads(STATE.read_text())
            try:
                await client.sign_in(st["phone"], sys.argv[2], phone_code_hash=st["hash"])
                me = await client.get_me()
                print(f"logged in as {me.first_name} (@{me.username})")
                STATE.unlink(missing_ok=True)
            except SessionPasswordNeededError:
                print("2FA enabled; run: python login.py password '<your password>'")
        elif cmd == "password":
            await client.sign_in(password=sys.argv[2])
            me = await client.get_me()
            print(f"logged in as {me.first_name} (@{me.username})")
            STATE.unlink(missing_ok=True)
        else:
            print(__doc__)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

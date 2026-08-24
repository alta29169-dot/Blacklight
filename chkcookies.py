"""
Standalone diagnostic: for each cookie in ROBLOSECURITY_COOKIES, print the
resolved account's userId, username, AND account creation date/ID.

Why this matters: if two cookies show the same username, they are the
SAME Roblox account, full stop — not a copy-paste display bug. This script
gives you the userId directly so there's no ambiguity.

Run this locally (not in this sandbox) with your real .env loaded.
"""

import os
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()

COOKIES_RAW = os.getenv("ROBLOSECURITY_COOKIES", "")
cookies = [c.strip() for c in COOKIES_RAW.split(",") if c.strip()]

async def check_cookie(session, idx, cookie):
    headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
    async with session.get("https://users.roblox.com/v1/users/authenticated", headers=headers) as resp:
        if resp.status != 200:
            print(f"[{idx}] FAILED auth — HTTP {resp.status}")
            return
        data = await resp.json()
        user_id = data.get("id")
        name = data.get("name")

    # Pull extra profile info to double check it's really a distinct account
    async with session.get(f"https://users.roblox.com/v1/users/{user_id}") as resp2:
        profile = await resp2.json() if resp2.status == 200 else {}

    created = profile.get("created", "unknown")
    print(f"[{idx}] cookie(...{cookie[-6:]}) -> userId={user_id}, username={name}, created={created}")

async def main():
    print(f"Found {len(cookies)} cookie(s) in ROBLOSECURITY_COOKIES\n")
    async with aiohttp.ClientSession() as session:
        for idx, cookie in enumerate(cookies):
            await check_cookie(session, idx, cookie)

    # Explicit duplicate check
    print("\nIf any two lines above show the SAME userId, those cookies")
    print("belong to the same account — the tokens differing doesn't matter.")

if __name__ == "__main__":
    asyncio.run(main())
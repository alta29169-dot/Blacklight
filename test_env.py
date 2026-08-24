"""
Diagnostic script to verify your .env setup before running the full bot.
Tests:
  1. .env variables loaded
  2. Discord connection + channel reachability
  3. Roblox cookies (primary + fallback) validity
  4. Presence API works per cookie
  5. BMMembers.txt exists and is parsable
  6. friends.json (optional — warns if missing but won't fail)
"""

import os
import sys
import asyncio
import aiohttp
import discord
from dotenv import load_dotenv

load_dotenv()

# ─── Config ────────────────────────────────────────────
DISCORD_TOKEN    = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL  = os.getenv("DISCORD_CHANNEL_IDS", "").split(",")[0].strip()
COOKIES_RAW      = os.getenv("ROBLOSECURITY_COOKIES", "")
MEMBERS_FILE     = os.getenv("MEMBERS_FILE", "BMMembers.txt")
FRIENDS_FILE     = os.getenv("FRIENDS_MAP_FILE", "friends.json")

OK = "✅"
ERR = "❌"

def bold(txt):
    return f"\033[1m{txt}\033[0m"

# ─── 1. .env checks ────────────────────────────────────
print(bold("── .env presence ──"))
checks = [
    ("DISCORD_TOKEN",       DISCORD_TOKEN),
    ("DISCORD_CHANNEL_IDS", DISCORD_CHANNEL),
    ("ROBLOSECURITY_COOKIES", COOKIES_RAW),
]
for name, val in checks:
    print(f"  {OK if val else ERR} {name}: {'***' if val and 'TOKEN' in name or 'COOKIE' in name else val}")

if not all(v for _, v in checks):
    print("\n⚠️  Missing critical env vars — stopping.")
    sys.exit(1)

cookies = [c.strip() for c in COOKIES_RAW.split(",") if c.strip()]
print(f"  → Found {len(cookies)} cookie(s)")

# ─── 2. BMMembers.txt ──────────────────────────────────
print(bold("\n── Members file ──"))
if os.path.exists(MEMBERS_FILE):
    with open(MEMBERS_FILE) as f:
        ids = [line.strip() for line in f if line.strip()]
    print(f"  {OK} {MEMBERS_FILE} exists with {len(ids)} IDs")
else:
    print(f"  {ERR} {MEMBERS_FILE} not found (will start empty)")

# ─── 3. friends.json ───────────────────────────────────
print(bold("\n── Friends map ──"))
if os.path.exists(FRIENDS_FILE):
    print(f"  {OK} {FRIENDS_FILE} found")
else:
    print(f"  ⚠️  {FRIENDS_FILE} not found (will only use primary cookie)")

# ─── 4. Roblox Cookies ─────────────────────────────────
async def test_roblox():
    print(bold("\n── Roblox Cookie Validation ──"))
    async with aiohttp.ClientSession() as session:
        for i, cookie in enumerate(cookies):
            label = "Primary" if i == 0 else f"Fallback #{i}"
            headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
            # Quick auth check via /users/authenticated
            try:
                async with session.get("https://users.roblox.com/v1/users/authenticated", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        name = data.get("name", "?")
                        print(f"  {OK} {label} cookie → authenticated as {name}")
                    else:
                        print(f"  {ERR} {label} cookie → HTTP {resp.status} (likely expired/invalid)")
            except Exception as e:
                print(f"  {ERR} {label} cookie → error: {e}")

        # Presence test with a known test ID (you can change this)
        test_ids = [261]  # Roblox account, public
        if os.path.exists(MEMBERS_FILE):
            with open(MEMBERS_FILE) as f:
                first_line = f.readline().strip()
                if first_line and first_line.isdigit():
                    test_ids = [int(first_line)]

        print(bold(f"\n── Presence test with IDs {test_ids} ──"))
        for i, cookie in enumerate(cookies):
            label = "Primary" if i == 0 else f"Fallback #{i}"
            headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
            payload = {"userIds": test_ids}
            try:
                async with session.post("https://presence.roblox.com/v1/presence/users", json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        presences = data.get("userPresences", [])
                        for p in presences:
                            ptype = {0:"Offline",1:"Online",2:"InGame"}.get(p.get("userPresenceType"),"?")
                            print(f"  {OK} {label} → {p.get('userId')}: {ptype}")
                    else:
                        print(f"  {ERR} {label} → HTTP {resp.status}")
            except Exception as e:
                print(f"  {ERR} {label} → {e}")

# ─── 5. Discord connection + channel ───────────────────
async def test_discord():
    print(bold("\n── Discord test ──"))
    intents = discord.Intents.default()
    bot = discord.Client(intents=intents)

    ready = asyncio.Event()

    @bot.event
    async def on_ready():
        ready.set()

    # Start bot in background
    loop = asyncio.get_running_loop()
    task = loop.create_task(bot.start(DISCORD_TOKEN))

    try:
        await asyncio.wait_for(ready.wait(), timeout=10)
        print(f"  {OK} Connected as {bot.user}")

        # Test channel
        channel = bot.get_channel(int(DISCORD_CHANNEL)) if DISCORD_CHANNEL.isdigit() else None
        if channel:
            try:
                await channel.send("🧪 Bot diagnostic test — if you see this, everything works!")
                print(f"  {OK} Sent test message to #{channel.name}")
            except discord.Forbidden:
                print(f"  {ERR} No permission to send in #{channel.name}")
            except Exception as e:
                print(f"  {ERR} Channel send error: {e}")
        else:
            print(f"  {ERR} Channel ID '{DISCORD_CHANNEL}' not found or invalid")
    except asyncio.TimeoutError:
        print(f"  {ERR} Discord login timed out (bad token?)")
    finally:
        await bot.close()
        task.cancel()

# ─── Main ──────────────────────────────────────────────
async def main():
    await test_roblox()
    await test_discord()
    print(bold("\n── Done ──"))

if __name__ == "__main__":
    asyncio.run(main())
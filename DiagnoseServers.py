"""
Diagnostic: replicate the SAME progressive-fallback presence check the real
bot uses (primary cookie first, then friends.json relays for anyone
unconfirmed) — not just the primary cookie alone. This matters because a
tracked member may only be presence-visible to a relay, not to your primary
account, depending on Roblox friend-visibility privacy settings.

Once we find someone genuinely in-game in the target game, we print their
exact presence data (placeId + gameId/job_id), then separately fetch the
FULL /servers/Public list for that placeId and check whether their job_id
genuinely appears anywhere in it, plus dump a sample server so you can see
what fields Roblox actually returns right now.

Run locally with your real .env loaded, from your bot's project folder.
"""

import os
import json
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()

COOKIES_RAW = os.getenv("ROBLOSECURITY_COOKIES", "")
cookies = [c.strip() for c in COOKIES_RAW.split(",") if c.strip()]
GAME_ID = int(os.getenv("ROBLOX_GAME_ID", "2210085102"))
FRIENDS_MAP_FILE = os.getenv("FRIENDS_MAP_FILE", "friends.json")

# Paste in a user ID you know is currently in-game to check specifically,
# or leave as None to scan for the first in-game hit across everyone.
TARGET_USER_ID = None

async def get_presence(session, user_ids, cookie):
    headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
    url = "https://presence.roblox.com/v1/presence/users"
    results = {}
    for i in range(0, len(user_ids), 100):
        chunk = user_ids[i:i+100]
        async with session.post(url, json={"userIds": chunk}, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                for p in data.get("userPresences", []):
                    results[p["userId"]] = p
            else:
                print(f"Presence fetch failed: HTTP {resp.status}")
    return results

async def dump_public_servers(session, place_id, target_job_id):
    url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?limit=50"
    page = 0
    total_servers = 0
    found = False
    sample_printed = False
    while url:
        async with session.get(url) as resp:
            print(f"  Page {page}: HTTP {resp.status}")
            if resp.status != 200:
                body = await resp.text()
                print(f"  Body: {body[:300]}")
                break
            data = await resp.json()
        servers = data.get("data", [])
        total_servers += len(servers)
        if servers and not sample_printed:
            print(f"  Sample server object fields: {list(servers[0].keys())}")
            print(f"  Sample server: {servers[0]}")
            sample_printed = True
        for s in servers:
            if s.get("id") == target_job_id:
                found = True
                print(f"  ✅ MATCH FOUND on page {page}: {s}")
        cursor = data.get("nextPageCursor")
        url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?limit=50&cursor={cursor}" if cursor else None
        page += 1
        await asyncio.sleep(0.3)

    print(f"\n  Total public servers seen across {page} page(s): {total_servers}")
    print(f"  Target job_id {target_job_id} found in public list: {found}")

async def main():
    if not os.path.exists("BMMembers.txt"):
        print("BMMembers.txt not found — run this from your bot's project folder.")
        return
    with open("BMMembers.txt") as f:
        user_ids = [int(l.strip()) for l in f if l.strip().isdigit()]

    friends_map = {}
    if os.path.exists(FRIENDS_MAP_FILE):
        with open(FRIENDS_MAP_FILE) as f:
            friends_map = json.load(f)

    async with aiohttp.ClientSession() as session:
        # ── Phase 1: primary cookie, everyone ──
        print(f"Checking presence for {len(user_ids)} members via PRIMARY cookie...")
        primary_results = await get_presence(session, user_ids, cookies[0])

        confirmed = {}
        unconfirmed = set(user_ids)
        for uid, data in primary_results.items():
            if data.get("userPresenceType", 0) in (1, 2):
                confirmed[uid] = data
                unconfirmed.discard(uid)

        print(f"Primary confirmed {len(confirmed)} online/in-game, "
              f"{len(unconfirmed)} still unconfirmed.\n")

        # ── Phase 2: relays, only for unconfirmed users on their friend list ──
        for relay_name, info in friends_map.items():
            if not unconfirmed:
                break
            idx = info.get("cookie_index", -1)
            if idx < 0 or idx >= len(cookies):
                continue
            friend_ids = set(info.get("friend_ids", []))
            targets = [uid for uid in unconfirmed if uid in friend_ids]
            if not targets:
                print(f"{relay_name}: no unconfirmed users overlap its friend list.")
                continue
            print(f"Checking {len(targets)} unconfirmed users via {relay_name}...")
            relay_results = await get_presence(session, targets, cookies[idx])
            for uid, data in relay_results.items():
                if data.get("userPresenceType", 0) in (1, 2):
                    confirmed[uid] = data
                    unconfirmed.discard(uid)
            print(f"  {relay_name} confirmed {sum(1 for u in targets if u in confirmed)} of {len(targets)} checked.\n")

        # ── Find someone actually in the target game ──
        candidates = TARGET_USER_ID and [TARGET_USER_ID] or list(confirmed.keys())
        target_uid = None
        target_data = None
        for uid in candidates:
            data = confirmed.get(uid)
            if data and data.get("userPresenceType") == 2 and data.get("placeId") == GAME_ID:
                target_uid = uid
                target_data = data
                break

        if not target_uid:
            print(f"No tracked member confirmed in-game in target game {GAME_ID}, "
                  f"even after checking primary + all relays. Either nobody's "
                  f"actually playing right now, or the game ID doesn't match. "
                  f"Confirmed online/in-game elsewhere: {len(confirmed)}")
            return

        job_id = target_data.get("gameId")
        place_id = target_data.get("placeId")
        print(f"\nTarget user {target_uid}:")
        print(f"  Raw presence data: {target_data}")
        print(f"  placeId = {place_id}")
        print(f"  gameId (job_id) = {job_id}\n")

        print(f"Scanning /servers/Public for placeId {place_id}...")
        await dump_public_servers(session, place_id, job_id)

if __name__ == "__main__":
    asyncio.run(main())
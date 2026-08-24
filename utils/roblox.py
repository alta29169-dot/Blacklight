import aiohttp
import asyncio
from typing import List, Dict, Optional, Tuple

# ─── User Fetch ───────────────────────────────────────
async def fetch_usernames(session: aiohttp.ClientSession, user_ids: List[int]) -> Dict[int, str]:
    """Fetch usernames for a list of user IDs. Returns {uid: username}."""
    url = "https://users.roblox.com/v1/users"
    members = {}
    for i in range(0, len(user_ids), 100):
        chunk = user_ids[i:i+100]
        payload = {"userIds": chunk, "excludeBannedUsers": True}
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for user in data.get("data", []):
                        members[user["id"]] = user["name"]
                else:
                    print(f"User fetch error: {resp.status}")
        except Exception as e:
            print(f"Exception during user fetch: {e}")
    return members

# ─── Presence Fetch (single cookie) ───────────────────
async def fetch_presence_batch(session: aiohttp.ClientSession, user_ids: List[int], cookie: str) -> Dict[int, dict]:
    """
    Fetch presence for a list of user IDs using a single cookie.
    Returns raw mapping: {userId: presenceData}
    Handles 429 with retries.
    """
    url = "https://presence.roblox.com/v1/presence/users"
    headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
    results = {}
    for i in range(0, len(user_ids), 100):
        chunk = user_ids[i:i+100]
        payload = {"userIds": chunk}
        retries = 3
        while retries > 0:
            try:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for presence in data.get("userPresences", []):
                            results[presence["userId"]] = presence
                        break  # success
                    elif resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", 5))
                        print(f"Rate limited, sleeping {retry_after}s")
                        await asyncio.sleep(retry_after)
                        retries -= 1
                    else:
                        print(f"Presence API error {resp.status} for chunk (cookie ending ...{cookie[-4:]})")
                        break
            except Exception as e:
                print(f"Exception during presence fetch: {e}")
                retries -= 1
                await asyncio.sleep(1)
        await asyncio.sleep(0.3)
    return results

# ─── Merge Presences (Progressive Fallback) ───────────
def merge_presences(presence_list: List[Dict[int, dict]]) -> Dict[int, dict]:
    """
    Given a list of presence results from different cookies (in order primary -> fallbacks),
    merge into a single dict per user, preferring the highest userPresenceType.
    """
    final = {}
    for batch in presence_list:
        for uid, data in batch.items():
            if uid not in final:
                final[uid] = data
            else:
                current_type = final[uid].get("userPresenceType", 0)
                new_type = data.get("userPresenceType", 0)
                if new_type > current_type:
                    final[uid] = data
    return final

# ─── Public Server Check ─────────────────────────────
async def find_public_server(session: aiohttp.ClientSession, place_id: int, job_id: str) -> Optional[dict]:
    """
    Check if a game server (job_id) is public. Returns server details or None.
    Handles 429 rate limits during page scraping.
    """
    url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?limit=50"
    pages_checked = 0
    servers_seen = 0

    while url:
        retries = 3
        data = None

        while retries > 0:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        break
                    elif resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", 5))
                        print(f"Rate limited checking server list, sleeping {retry_after}s")
                        await asyncio.sleep(retry_after)
                        retries -= 1
                    else:
                        return None
            except Exception as e:
                print(f"Error fetching server list: {e}")
                retries -= 1
                await asyncio.sleep(1)

        if not data:
            return None

        pages_checked += 1
        page_servers = data.get("data", [])
        servers_seen += len(page_servers)

        for server in page_servers:
            if server.get("id") == job_id:
                return server

        cursor = data.get("nextPageCursor")
        if not cursor and servers_seen >= 650 and servers_seen % 700 >= 650:
            print(f"⚠️ Public server pagination for place {place_id} stopped after "
                  f"~{servers_seen} servers — this may be Roblox's known pagination "
                  f"cutoff bug. Server {job_id} may be public but unreachable.")

        url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?limit=50&cursor={cursor}" if cursor else None
        
        # Gentle delay between page fetches to protect IP rate limits
        await asyncio.sleep(0.2)

    return None

async def check_multiple_servers(session: aiohttp.ClientSession, place_id: int, job_ids: List[str]) -> Dict[str, Optional[dict]]:
    """Concurrently check a list of server job_ids for public status."""
    tasks = [find_public_server(session, place_id, jid) for jid in job_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    mapping = {}
    for jid, res in zip(job_ids, results):
        if isinstance(res, Exception):
            print(f"Error checking server {jid}: {res}")
            mapping[jid] = None
        else:
            mapping[jid] = res
    return mapping

# ─── Friends Fetcher ─────────────────────────────
async def fetch_friends(session: aiohttp.ClientSession, user_id: int, cookie: str) -> List[int]:
    """
    Fetch all friend IDs for a given user.
    Handles pagination and rate limits.
    """
    url = f"https://friends.roblox.com/v1/users/{user_id}/friends?limit=100"
    headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
    friend_ids = []

    while url:
        retries = 3
        while retries > 0:
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for friend in data.get("data", []):
                            friend_ids.append(friend["id"])
                        cursor = data.get("nextPageCursor")
                        url = f"https://friends.roblox.com/v1/users/{user_id}/friends?limit=100&cursor={cursor}" if cursor else None
                        break
                    elif resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", 5))
                        print(f"Rate limited fetching friends, sleeping {retry_after}s")
                        await asyncio.sleep(retry_after)
                        retries -= 1
                    else:
                        body_text = await resp.text()
                        print(f"Friends API error {resp.status} for user {user_id}: {body_text[:300]}")
                        return friend_ids
            except Exception as e:
                print(f"Exception fetching friends: {e}")
                retries -= 1
                await asyncio.sleep(1)
        await asyncio.sleep(0.3)
    return friend_ids
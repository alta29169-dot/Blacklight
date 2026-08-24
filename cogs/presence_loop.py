import discord
from discord.ext import commands, tasks
from datetime import datetime
import asyncio
import aiohttp
from utils.roblox import (
    fetch_presence_batch,
    merge_presences,
    fetch_usernames,
    check_multiple_servers
)
from config import (
    ROBLOSECURITY_COOKIES,
    ROBLOX_GAME_ID,
    MEMBERS_FILE,
    PRESENCE_INTERVAL_MINUTES,
    DEFAULT_ALERT_THRESHOLD,
    load_threshold,
    save_threshold,
    load_friends_map,
    DISCORD_CHANNEL_IDS,
    DISCORD_ROLE_IDS
)

class PresenceLoop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        from config import load_settings
        self.bot = bot
        self.member_cache = {}  # {user_id: username}
        self.presence_cache = {}  # {user_id: presence_data}
        self.was_in_game = {}
        self.session_starts = {}
        self.threshold_alerted = False
        self.alert_threshold, self.min_population = load_settings()
        self.cookies = ROBLOSECURITY_COOKIES
        self.friends_map = load_friends_map()
        self._session = None
        
        # Max 3 concurrent Roblox API requests to prevent 429 Too Many Requests
        self.semaphore = asyncio.Semaphore(3)

    async def cog_load(self):
        # DummyCookieJar prevents cookies from bleeding between requests on the same session
        self._session = aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar())
        await self.load_members()
        self.presence_loop.start()

    async def cog_unload(self):
        self.presence_loop.cancel()
        if self._session:
            await self._session.close()

    async def load_members(self):
        try:
            with open(MEMBERS_FILE, "r") as f:
                user_ids = set(int(line.strip()) for line in f if line.strip())
        except FileNotFoundError:
            print(f"Members file {MEMBERS_FILE} not found. Starting with friend-list members only.")
            user_ids = set()

        friend_referenced_ids = set()
        for info in self.friends_map.values():
            friend_referenced_ids.update(info.get("friend_ids", []))

        added_from_friends = friend_referenced_ids - user_ids
        user_ids |= friend_referenced_ids
        user_ids = sorted(user_ids)

        if not user_ids:
            print("No members to track from either the members file or friends.json.")
            self.member_cache = {}
            return

        print(f"\n── Loading {len(user_ids)} members "
              f"({len(added_from_friends)} added via friends.json) ──")
        self.member_cache = await fetch_usernames(self._session, user_ids)
        print(f"Tracking {len(self.member_cache)} members\n")

    async def _safe_fetch_presence(self, target_ids, cookie, fallback_name="Primary"):
        """Helper to fetch presence with a concurrency limit and basic retries."""
        async with self.semaphore:
            for attempt in range(3):
                try:
                    return await fetch_presence_batch(self._session, target_ids, cookie)
                except Exception as e:
                    if attempt == 2:
                        print(f"[{fallback_name}] Failed after 3 attempts: {e}")
                        return {}
                    await asyncio.sleep(2 ** attempt) # Exponential backoff

    @tasks.loop(minutes=PRESENCE_INTERVAL_MINUTES)
    async def presence_loop(self):
        await self.refresh_presence()
        await self.check_alerts()

    async def refresh_presence(self):
        if not self.member_cache:
            return

        user_ids = list(self.member_cache.keys())
        
        # ── Cleanup Stale Data (Memory Leak Fix) ──
        tracked_set = set(user_ids)
        self.was_in_game = {uid: state for uid, state in self.was_in_game.items() if uid in tracked_set}
        self.session_starts = {uid: start for uid, start in self.session_starts.items() if uid in tracked_set}

        # ── Phase 1: Primary cookie queries all users ──
        primary_cookie = self.cookies[0]
        print("Querying primary cookie...")
        primary_results = await self._safe_fetch_presence(user_ids, primary_cookie, "Primary")
        
        confirmed = {}  
        unconfirmed = set(user_ids)

        for uid, data in primary_results.items():
            if data.get("userPresenceType", 0) in (1, 2):
                confirmed[uid] = data
                unconfirmed.discard(uid)

        # ── Phase 2: Fallback cookies query concurrently ──
        tasks = []
        for fallback_name, info in self.friends_map.items():
            if not unconfirmed:
                break
            
            cookie_index = info.get("cookie_index", -1)
            if cookie_index < 0 or cookie_index >= len(self.cookies):
                continue
            
            friend_ids = set(info.get("friend_ids", []))
            target_ids = [uid for uid in unconfirmed if uid in friend_ids]
            
            if target_ids:
                cookie = self.cookies[cookie_index]
                print(f"Queuing fallback '{fallback_name}' for {len(target_ids)} users...")
                tasks.append(self._safe_fetch_presence(target_ids, cookie, fallback_name))

        if tasks:
            # Execute all fallback queries at the same time
            fallback_results_list = await asyncio.gather(*tasks)
            for fallback_results in fallback_results_list:
                for uid, data in fallback_results.items():
                    if data.get("userPresenceType", 0) in (1, 2):
                        confirmed[uid] = data
                        unconfirmed.discard(uid)

        # ── Assemble final presence ──
        final_presence = {}
        for uid in user_ids:
            if uid in confirmed:
                final_presence[uid] = confirmed[uid]
            elif uid in primary_results:
                final_presence[uid] = primary_results[uid]
            else:
                final_presence[uid] = {
                    "userId": uid,
                    "userPresenceType": 0,
                    "placeId": None,
                    "gameId": None
                }

        # ── Detect joins/leaves ──
        for uid in user_ids:
            presence = final_presence.get(uid, {})
            in_game = presence.get("userPresenceType") == 2
            game_id = presence.get("placeId")
            in_target = in_game and game_id == ROBLOX_GAME_ID
            previously = self.was_in_game.get(uid, False)

            if in_target and not previously:
                self.session_starts[uid] = datetime.now()
                self.was_in_game[uid] = True
                print(f"{self.member_cache.get(uid, uid)} joined the game")
            elif not in_target and previously:
                self.was_in_game[uid] = False
                start = self.session_starts.pop(uid, None)
                if start:
                    duration = datetime.now() - start
                    minutes = int(duration.total_seconds() // 60)
                    print(f"{self.member_cache.get(uid, uid)} left after {minutes} min")

        self.presence_cache = {uid: {
            "type": final_presence[uid]["userPresenceType"],
            "in_target": final_presence[uid].get("userPresenceType") == 2 and final_presence[uid].get("placeId") == ROBLOX_GAME_ID,
            "username": self.member_cache.get(uid, f"Unknown ({uid})"),
            "job_id": final_presence[uid].get("gameId"),
            "place_id": final_presence[uid].get("placeId"),
        } for uid in user_ids}

    async def check_alerts(self, interaction: discord.Interaction = None, force: bool = False):
        in_target_members = {
            uid: v for uid, v in self.presence_cache.items() if v["in_target"]
        }
        if not in_target_members:
            if self.threshold_alerted:
                self.threshold_alerted = False
            if interaction:
                await interaction.followup.send("No tracked members are currently in the game.")
            return

        unique_job_ids = {}
        for uid, v in in_target_members.items():
            jid = v.get("job_id")
            pid = v.get("place_id")
            if jid and jid not in unique_job_ids:
                unique_job_ids[jid] = pid

        server_details_cache = {}
        if unique_job_ids:
            job_ids = list(unique_job_ids.keys())
            print(f"Checking {len(job_ids)} unique servers...")
            # We now safely reuse the persistent session for server checks
            server_details_cache = await check_multiple_servers(self._session, ROBLOX_GAME_ID, job_ids)

        public_members = {}
        for uid, v in in_target_members.items():
            jid = v.get("job_id")
            details = server_details_cache.get(jid)
            if details and details.get("playing", 0) >= self.min_population:
                public_members[uid] = v

        in_game_count = len(public_members)
        meets_threshold = in_game_count >= self.alert_threshold

        if not public_members:
            if interaction:
                await interaction.followup.send("Tracked members are in-game, but none are in public servers.")
            return

        should_send = force or (meets_threshold and not self.threshold_alerted)

        if should_send:
            await self.send_alert(public_members, server_details_cache, unique_job_ids, interaction=interaction)

        if meets_threshold:
            self.threshold_alerted = True
        else:
            if self.threshold_alerted:
                print(f"Public count dropped below {self.alert_threshold} — alert reset")
            self.threshold_alerted = False

    async def send_alert(self, public_members, server_details_cache, unique_job_ids, interaction: discord.Interaction = None):
        servers_grouped = {}
        for uid, v in public_members.items():
            jid = v["job_id"]
            if jid not in servers_grouped:
                servers_grouped[jid] = []
            servers_grouped[jid].append(v["username"])

        total_members = len(public_members)
        total_servers = len(servers_grouped)

        embed = discord.Embed(
            title="Active Players Ingame",
            description=f"**{total_members}** member{'s are' if total_members > 1 else ' is'} currently in-game across **{total_servers}** server{'s' if total_servers > 1 else ''}.",
            color=0x2B2D31,  
            timestamp=datetime.now()
        )

        for jid, names in servers_grouped.items():
            details = server_details_cache.get(jid)
            
            playing = details.get("playing", "?") if details else "?"
            max_players = details.get("maxPlayers", "?") if details else "?"
            fps = details.get("fps", "?") if details else "?"
            ping = details.get("ping", "?") if details else "?"

            if isinstance(fps, float):
                fps = round(fps, 1)
            if isinstance(ping, float):
                ping = round(ping, 1)

            pid = unique_job_ids.get(jid)
            
            stats_str = f"Players: {playing}/{max_players} | FPS: {fps} | Ping: {ping}ms"
            formatted_names = "\n".join([f"• {name}" for name in names])
            join_link = f"[Server Link](https://www.roblox.com/games/{pid}?gameInstanceId={jid})" if pid else "*Link Unavailable*"

            field_value = f"{stats_str}\n\n**Tracked Members:**\n{formatted_names}\n\nLink: {join_link}"
            
            embed.add_field(
                name=f"Server Instance ({jid[:8]}...)",
                value=field_value,
                inline=False
            )

        embed.set_footer(text="MDB Tech")

        if interaction:
            role_mentions = " ".join([
                interaction.guild.get_role(role_id).mention
                for role_id in DISCORD_ROLE_IDS
                if interaction.guild.get_role(role_id)
            ])
            content = role_mentions if role_mentions else None
            await interaction.followup.send(content=content, embed=embed)
            return

        for channel_id in DISCORD_CHANNEL_IDS:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue
                
            role_mentions = " ".join([
                channel.guild.get_role(role_id).mention
                for role_id in DISCORD_ROLE_IDS
                if channel.guild.get_role(role_id)
            ])
            content = role_mentions if role_mentions else None
            
            await channel.send(content=content, embed=embed)

        print(f"Threshold of {self.alert_threshold} reached — alert sent! ({total_members} members public)")

    @presence_loop.before_loop
    async def before_presence_loop(self):
        await self.bot.wait_until_ready()

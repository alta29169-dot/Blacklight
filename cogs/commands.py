import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from typing import Optional
import asyncio
import aiohttp
from utils.permissions import allowed_command
from utils.roblox import check_multiple_servers
from config import (
    MEMBERS_FILE,
    ROBLOX_GAME_ID,
    load_threshold,
    save_threshold,
    save_settings
)

class TrackedPaginator(discord.ui.View):
    """Interactive View for navigating pages of tracked members."""
    def __init__(self, items: list[tuple[int, str]], per_page: int = 15):
        super().__init__(timeout=180)  # Buttons deactivate after 3 minutes
        self.items = items
        self.per_page = per_page
        self.current_page = 0
        self.max_pages = max(1, (len(items) + per_page - 1) // per_page)
        self.update_button_states()

    def update_button_states(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.max_pages - 1

    def create_embed(self) -> discord.Embed:
        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        page_items = self.items[start_idx:end_idx]

        lines = [f"• {username}: ```{uid}```" for uid, username in page_items]
        formatted_list = "\n".join(lines) if lines else "*No members found.*"

        embed = discord.Embed(
            title="Tracked Members",
            description=f"Total Members: **{len(self.items)}**\n\n{formatted_list}",
            color=0x2b2d31,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"EHKB Tech • Page {self.current_page + 1} of {self.max_pages}")
        return embed

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary, custom_id="prev_page")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_button_states()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="next_page")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            self.update_button_states()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)


class Commands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_presence_cog(self):
        return self.bot.get_cog("PresenceLoop")

    @app_commands.command(name="status", description="Show current member activity breakdown")
    @allowed_command()
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cog = self.get_presence_cog()
        if not cog:
            await interaction.followup.send("System not ready.")
            return

        presence = cog.presence_cache
        in_target = [v for v in presence.values() if v["in_target"]]
        online_other = [v for v in presence.values() if v["type"] in (1, 2) and not v["in_target"]]
        offline = [v for v in presence.values() if v["type"] == 0]

        embed = discord.Embed(
            title="Member Status Overview",
            color=0x2b2d31,
            timestamp=datetime.now()
        )
        
        stats_line = f"InGame: {len(in_target)} | Online: {len(online_other)} | Offline: {len(offline)} | Total: {len(presence)}"
        
        if in_target:
            names = "\n".join([f"• {v['username']}" for v in in_target[:20]])
            if len(in_target) > 20:
                names += f"\n*...and {len(in_target) - 20} more*"
            embed.description = f"{stats_line}\n\n**Currently In Game:**\n{names}"
        else:
            embed.description = f"{stats_line}\n\nNo members are currently in the game."

        embed.set_footer(text="EHKB Tech")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="tracked", description="List or search tracked members")
        @app_commands.describe(search="Optional username search (case-insensitive)")
        @allowed_command()
        async def tracked(self, interaction: discord.Interaction, search: Optional[str] = None):
            await interaction.response.defer()
            cog = self.get_presence_cog()
            if not cog:
                await interaction.followup.send("System not ready.")
                return
            member_cache = cog.member_cache
            if not member_cache:
                await interaction.followup.send("No members are currently tracked.")
                return
    
            items = list(member_cache.items())  # List of (uid, username)
    
            # Filter items if a search term was provided
            if search:
                query = search.strip().lower()
                items = [(uid, name) for uid, name in items if query in name.lower()]
                
                if not items:
                    await interaction.followup.send(f"No tracked members found matching '{search}'.")
                    return
    
            paginator = TrackedPaginator(items=items, per_page=15)
            
            # If there's only 1 page, don't show the navigation buttons
            if paginator.max_pages == 1:
                await interaction.followup.send(embed=paginator.create_embed())
            else:
                await interaction.followup.send(embed=paginator.create_embed(), view=paginator)
            
    @app_commands.command(name="addmember", description="Add a Roblox user ID to track")
    @app_commands.describe(user_id="Roblox user ID")
    @allowed_command()
    async def addmember(self, interaction: discord.Interaction, user_id: str):
        await interaction.response.defer()
        cog = self.get_presence_cog()
        if not cog:
            await interaction.followup.send("System not ready.")
            return

        try:
            uid = int(user_id)
        except ValueError:
            await interaction.followup.send("Invalid user ID provided.")
            return

        if uid in cog.member_cache:
            await interaction.followup.send(f"User ID `{uid}` is already being tracked.")
            return

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://users.roblox.com/v1/users",
                json={"userIds": [uid], "excludeBannedUsers": True}
            ) as resp:
                data = await resp.json()

        users = data.get("data", [])
        if not users:
            await interaction.followup.send(f"Could not find a Roblox user associated with ID `{uid}`.")
            return

        username = users[0]["name"]
        cog.member_cache[uid] = username

        with open(MEMBERS_FILE, "a") as f:
            f.write(f"\n{uid}")

        embed = discord.Embed(
            title="Member Added",
            description=f"Now tracking **{username}** (`{uid}`)",
            color=0x2b2d31,
            timestamp=datetime.now()
        )
        embed.set_footer(text="EHKB Tech")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="removemember", description="Remove a Roblox user ID from tracking")
    @app_commands.describe(user_id="Roblox user ID")
    @allowed_command()
    async def removemember(self, interaction: discord.Interaction, user_id: str):
        await interaction.response.defer()
        cog = self.get_presence_cog()
        if not cog:
            await interaction.followup.send("System not ready.")
            return

        try:
            uid = int(user_id)
        except ValueError:
            await interaction.followup.send("Invalid user ID provided.")
            return

        if uid not in cog.member_cache:
            await interaction.followup.send(f"User ID `{uid}` is not currently tracked.")
            return

        username = cog.member_cache.pop(uid)
        cog.was_in_game.pop(uid, None)
        cog.session_starts.pop(uid, None)
        cog.presence_cache.pop(uid, None)

        with open(MEMBERS_FILE, "r") as f:
            lines = f.readlines()
        with open(MEMBERS_FILE, "w") as f:
            f.writelines([l for l in lines if l.strip() != str(uid)])

        embed = discord.Embed(
            title="Member Removed",
            description=f"Stopped tracking **{username}** (`{uid}`)",
            color=0x2b2d31,
            timestamp=datetime.now()
        )
        embed.set_footer(text="EHKB Tech")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="setthreshold", description="Set the alert threshold")
    @app_commands.describe(count="Minimum members in game before pinging")
    @allowed_command()
    async def setthreshold(self, interaction: discord.Interaction, count: int):
        await interaction.response.defer()
        cog = self.get_presence_cog()
        if not cog:
            await interaction.followup.send("System not ready.")
            return

        cog.alert_threshold = count
        cog.threshold_alerted = False
        save_threshold(count)

        embed = discord.Embed(
            title="Threshold Updated",
            description=f"Alert threshold configured to **{count}** member{'s' if count > 1 else ''}.",
            color=0x2b2d31,
            timestamp=datetime.now()
        )
        embed.set_footer(text="EHKB Tech")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="setminpop", description="Set minimum server population before alerting")
    @app_commands.describe(count="Minimum total players in a server")
    @allowed_command()
    async def setminpop(self, interaction: discord.Interaction, count: int):
        await interaction.response.defer()
        cog = self.get_presence_cog()
        if not cog:
            await interaction.followup.send("System not ready.")
            return

        cog.min_population = count
        save_settings(cog.alert_threshold, count)

        embed = discord.Embed(
            title="Minimum Population Updated",
            description=f"Minimum server population set to **{count}** player{'s' if count > 1 else ''}.",
            color=0x2b2d31,
            timestamp=datetime.now()
        )
        embed.set_footer(text="EHKB Tech")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="forceping", description="Force an alert for all members currently in the game")
    @allowed_command()
    async def forceping(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cog = self.get_presence_cog()
        if not cog:
            await interaction.followup.send("System not ready.")
            return

        # Run a fresh presence pass instead of relying on presence_cache,
        # which may be up to PRESENCE_INTERVAL_MINUTES stale if someone
        # joined since the last scheduled loop tick.
        await interaction.followup.send("Running a fresh presence scan...")
        await cog.refresh_presence()

        # force=True guarantees an alert goes out even if the automatic loop
        # already pinged for this exact state; check_alerts also syncs
        # threshold_alerted afterward so the *next* automatic tick won't
        # turn around and double-ping the same group again.
        await cog.check_alerts(interaction=interaction, force=True)

    @app_commands.command(name="relaysync", description="Rebuild the internal relay index used for presence tracking")
    @allowed_command()
    async def relaysync(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cog = self.get_presence_cog()
        if not cog:
            await interaction.followup.send("System not ready.")
            return
    
        cookies = cog.cookies
        if len(cookies) < 2:
            await interaction.followup.send("Only one relay configured — nothing to sync.")
            return
    
        # Load master member list
        from config import MASTER_MEMBERS_FILE
        try:
            with open(MASTER_MEMBERS_FILE, "r") as f:
                master_ids = set(int(line.strip()) for line in f if line.strip())
        except FileNotFoundError:
            await interaction.followup.send(f"Master list `{MASTER_MEMBERS_FILE}` not found.")
            return
    
        if not master_ids:
            await interaction.followup.send("Master list is empty.")
            return
    
        import aiohttp
        from config import FRIENDS_MAP_FILE
        from utils.roblox import fetch_friends
    
        # IMPORTANT: use a SEPARATE ClientSession per cookie/account.
        # aiohttp.ClientSession keeps its own internal cookie jar, and reusing
        # one session across multiple .ROBLOSECURITY identities lets
        # Set-Cookie responses from one account bleed into requests made
        # "as" another account later in the loop — even though each request
        # explicitly passes its own Cookie header. This caused relay_1 and
        # relay_2 to resolve to the same friend list despite different cookies.
        #
        # PACING: with only 2-3 relays back-to-back requests were fine, but
        # as relay count grows this loop can trip Roblox's rate limits faster
        # than fetch_friends' internal retry logic can gracefully absorb.
        # Add a small delay between relays, plus explicit 429 handling here
        # (this auth call previously had none — a 429 just silently marked
        # the relay as failed instead of retrying).
        relay_ids = {}
        for idx, cookie in enumerate(cookies):
            headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
            retries = 3
            while retries > 0:
                async with aiohttp.ClientSession() as auth_session:
                    async with auth_session.get("https://users.roblox.com/v1/users/authenticated", headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            relay_ids[idx] = data["id"]
                            break
                        elif resp.status == 429:
                            retry_after = int(resp.headers.get("Retry-After", 5))
                            print(f"Relay #{idx} auth rate limited, sleeping {retry_after}s")
                            await asyncio.sleep(retry_after)
                            retries -= 1
                        else:
                            relay_ids[idx] = None
                            # Surface auth failures instead of silently continuing —
                            # this is the most common reason node counts come back as 0.
                            await interaction.followup.send(
                                f"⚠️ Relay #{idx} failed authentication (HTTP {resp.status}). "
                                f"That relay is likely expired/invalid, so relay_{idx} will show 0 nodes."
                            )
                            break
            else:
                # Retries exhausted on repeated 429s
                relay_ids[idx] = None
                await interaction.followup.send(
                    f"⚠️ Relay #{idx} kept getting rate limited during auth — skipping this run."
                )

            # Gentle pacing between relays regardless of outcome
            if idx < len(cookies) - 1:
                await asyncio.sleep(2)

        # Fetch friends for each fallback cookie
        new_map = {}
        for idx, cookie in enumerate(cookies[1:], start=1):
            relay_name = f"relay_{idx}"
            user_id = relay_ids.get(idx)
            if not user_id:
                new_map[relay_name] = {"cookie_index": idx, "friend_ids": []}
                continue

            await interaction.followup.send(f"Syncing relay #{idx}...")
            async with aiohttp.ClientSession() as friend_session:
                friends = await fetch_friends(friend_session, user_id, cookie)
            # Cross-reference with master list — captures everyone, not just active tracked
            tracked_friends = [fid for fid in friends if fid in master_ids]
            new_map[relay_name] = {
                "cookie_index": idx,
                "friend_ids": tracked_friends
            }
            # Surface RAW count vs matched count — if raw is 0 the fetch itself
            # is failing (bad cookie/HTTP error); if raw is >0 but matched is 0, the
            # matching logic or master list is the problem instead.
            await interaction.followup.send(
                f"Relay #{idx}: indexed **{len(friends)}** total nodes, "
                f"**{len(tracked_friends)}** match the master list."
            )
            print(f"Relay #{idx} raw nodes: {len(friends)}, matched to master list: {len(tracked_friends)}")

            # Gentle pacing between relays — friend lists can be large (up to
            # 200 each) and each one is already its own paginated fetch inside
            # fetch_friends. Spacing out the relays themselves avoids stacking
            # multiple large pulls back-to-back as relay count grows.
            if idx < len(cookies) - 1:
                await asyncio.sleep(3)

        # Write to friends.json
        import json
        with open(FRIENDS_MAP_FILE, "w") as f:
            json.dump(new_map, f, indent=2)

        # Reload friends_map, then rebuild member_cache so anyone newly
        # discovered as a relay's friend (and therefore verified on the
        # master list) actually gets added to what the presence loop
        # tracks — otherwise they'd sit unused in friends.json until the
        # bot restarted and re-ran load_members() at startup.
        from config import load_friends_map
        cog.friends_map = load_friends_map()
        await interaction.followup.send("Rebuilding tracked member list with newly discovered relay friends...")
        await cog.load_members()
    
        # Summary embed
        embed = discord.Embed(
            title="Relay Sync Complete",
            description=f"Cross-referenced against `{MASTER_MEMBERS_FILE}` ({len(master_ids)} members).",
            color=0x2b2d31,
            timestamp=datetime.now()
        )
        total_covered = sum(len(info["friend_ids"]) for info in new_map.values())
        for name, info in new_map.items():
            count = len(info["friend_ids"])
            embed.add_field(name=name, value=f"{count} nodes covered", inline=False)
        embed.add_field(name="Total Coverage", value=f"{total_covered} signal paths mapped across all relays", inline=False)
        embed.set_footer(text="EHKB Tech")
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Commands(bot))

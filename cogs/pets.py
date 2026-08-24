import json
import random
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

PETS_FILE = "pets.json"

# ── Realms ─────────────────────────────────────────────
# (name, emoji, min_level, max_level, breakthrough_success_chance)
REALMS = [
    ("Hatchling",  "🥚", 1,   9,   1.00),  # no breakthrough needed to enter
    ("Awakened",   "🐾", 10,  24,  0.80),
    ("Ferocious",  "🔥", 25,  49,  0.70),
    ("Alpha",      "⚡", 50,  99,  0.60),
    ("Mythic",     "🌟", 100, 199, 0.50),
    ("Ascendant",  "👑", 200, 999999, 0.40),
]

def get_realm_index(level: int) -> int:
    for i, (_, _, lo, hi, _) in enumerate(REALMS):
        if lo <= level <= hi:
            return i
    return len(REALMS) - 1

def get_realm(level: int):
    return REALMS[get_realm_index(level)]

def xp_to_next(level: int) -> int:
    return 100 * level

def is_at_realm_cap(level: int) -> bool:
    _, _, lo, hi, _ = get_realm(level)
    return level >= hi and get_realm_index(level) < len(REALMS) - 1

def compute_power(pet: dict) -> int:
    level = pet["level"]
    vitality = pet["happiness"] + pet["energy"] - pet["hunger"]  # -100..200
    return max(1, level * 10 + vitality // 3)

def make_bar(value: int, length: int = 10) -> str:
    filled = max(0, min(length, value * length // 100))
    return "█" * filled + "░" * (length - filled)

def default_pet(name: str) -> dict:
    return {
        "name": name,
        "level": 1,
        "xp": 0,
        "hunger": 50,
        "happiness": 50,
        "energy": 50,
        "wins": 0,
        "losses": 0,
        "breakthrough_fails": 0,
    }

def get_ascii_art(pet: dict) -> str:
    if pet["hunger"] > 80:
        return r"( >_< )  *stomach rumbles*"
    elif pet["happiness"] < 30:
        return r"( T_T )  *feeling lonely...*"
    elif pet["energy"] < 20:
        return r"( -_- )  zzz..."
    else:
        return r"( o.o )  *happy & alert!*"


class Pets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pets = self.load_pets()

    # ── Persistence ────────────────────────────────────
    def load_pets(self) -> dict:
        try:
            with open(PETS_FILE, "r") as f:
                return {int(k): v for k, v in json.load(f).items()}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_pets(self):
        with open(PETS_FILE, "w") as f:
            json.dump({str(k): v for k, v in self.pets.items()}, f, indent=2)

    def get_pet(self, user_id: int, create_name: str = None) -> dict:
        if user_id not in self.pets:
            self.pets[user_id] = default_pet(create_name or "Pet")
        return self.pets[user_id]

    # ── Shared XP/level logic ──────────────────────────
    def add_xp(self, pet: dict, amount: int) -> list[str]:
        """Adds XP, handles level-ups (capped at realm boundary). Returns event log lines."""
        events = []
        pet["xp"] += amount
        while pet["xp"] >= xp_to_next(pet["level"]) and not is_at_realm_cap(pet["level"]):
            pet["xp"] -= xp_to_next(pet["level"])
            pet["level"] += 1
            events.append(f"⬆️ Leveled up to **Level {pet['level']}**!")
        if is_at_realm_cap(pet["level"]) and pet["xp"] >= xp_to_next(pet["level"]):
            pet["xp"] = xp_to_next(pet["level"])  # cap XP, waiting on breakthrough
        return events

    def embed_color(self, level: int) -> int:
        return 0x2b2d31

    # ── Status Display ──────────────────────────────────
    @app_commands.command(name="pet", description="View your pet's status")
    async def pet(self, interaction: discord.Interaction):
        pet = self.get_pet(interaction.user.id, create_name=interaction.user.display_name)
        self.save_pets()

        realm_name, realm_emoji, _, realm_hi, _ = get_realm(pet["level"])
        power = compute_power(pet)
        at_cap = is_at_realm_cap(pet["level"])

        embed = discord.Embed(
            title=f"{realm_emoji} {pet['name']} — {realm_name} Realm",
            description=f"```{get_ascii_art(pet)}```",
            color=self.embed_color(pet["level"]),
            timestamp=datetime.now()
        )
        embed.add_field(name="Level", value=f"**{pet['level']}**" + (" (CAPPED)" if at_cap else ""), inline=True)
        embed.add_field(name="Power", value=f"**{power}**", inline=True)
        embed.add_field(name="Record", value=f"{pet['wins']}W / {pet['losses']}L", inline=True)

        if at_cap:
            embed.add_field(
                name="XP",
                value=f"`{make_bar(100)}` MAX — ready for `/breakthrough`!",
                inline=False
            )
        else:
            xp_pct = int(pet["xp"] * 100 / xp_to_next(pet["level"]))
            embed.add_field(
                name="XP",
                value=f"`{make_bar(xp_pct)}` {pet['xp']}/{xp_to_next(pet['level'])}",
                inline=False
            )

        embed.add_field(name="Hunger", value=f"`{make_bar(pet['hunger'])}` {pet['hunger']}/100", inline=False)
        embed.add_field(name="Happiness", value=f"`{make_bar(pet['happiness'])}` {pet['happiness']}/100", inline=False)
        embed.add_field(name="Energy", value=f"`{make_bar(pet['energy'])}` {pet['energy']}/100", inline=False)

        embed.set_footer(text="EHKB Tech")
        await interaction.response.send_message(embed=embed)

    # ── Care Actions ─────────────────────────────────────
    @app_commands.command(name="feed", description="Feed your pet")
    async def feed(self, interaction: discord.Interaction):
        pet = self.get_pet(interaction.user.id, create_name=interaction.user.display_name)
        pet["hunger"] = max(0, pet["hunger"] - 30)
        pet["energy"] = min(100, pet["energy"] + 5)
        events = self.add_xp(pet, 10)
        self.save_pets()

        desc = f"You fed **{pet['name']}**! Delicious. (+10 XP)"
        if events:
            desc += "\n" + "\n".join(events)
        embed = discord.Embed(description=desc, color=self.embed_color(pet["level"]))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="play", description="Play with your pet")
    async def play(self, interaction: discord.Interaction):
        pet = self.get_pet(interaction.user.id, create_name=interaction.user.display_name)
        if pet["energy"] < 15:
            await interaction.response.send_message(f"**{pet['name']}** is too tired to play! Try `/sleep` first.")
            return

        pet["happiness"] = min(100, pet["happiness"] + 25)
        pet["hunger"] = min(100, pet["hunger"] + 15)
        pet["energy"] = max(0, pet["energy"] - 20)
        events = self.add_xp(pet, 20)
        self.save_pets()

        desc = f"You played fetch with **{pet['name']}**! (+20 XP)"
        if events:
            desc += "\n" + "\n".join(events)
        embed = discord.Embed(description=desc, color=self.embed_color(pet["level"]))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="sleep", description="Let your pet rest")
    async def sleep(self, interaction: discord.Interaction):
        pet = self.get_pet(interaction.user.id, create_name=interaction.user.display_name)
        pet["energy"] = 100
        pet["hunger"] = min(100, pet["hunger"] + 20)
        events = self.add_xp(pet, 10)
        self.save_pets()

        desc = f"**{pet['name']}** took a long nap and feels restored! (+10 XP)"
        if events:
            desc += "\n" + "\n".join(events)
        embed = discord.Embed(description=desc, color=self.embed_color(pet["level"]))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rename", description="Rename your pet")
    @app_commands.describe(name="New name for your pet")
    async def rename(self, interaction: discord.Interaction, name: str):
        pet = self.get_pet(interaction.user.id, create_name=interaction.user.display_name)
        old_name = pet["name"]
        pet["name"] = name[:32]
        self.save_pets()
        await interaction.response.send_message(f"**{old_name}** shall now be known as **{pet['name']}**!")

    # ── Breakthrough ──────────────────────────────────────
    @app_commands.command(name="breakthrough", description="Attempt to break through to the next realm")
    async def breakthrough(self, interaction: discord.Interaction):
        pet = self.get_pet(interaction.user.id, create_name=interaction.user.display_name)

        if not is_at_realm_cap(pet["level"]):
            xp_needed = xp_to_next(pet["level"]) - pet["xp"]
            await interaction.response.send_message(
                f"**{pet['name']}** isn't ready yet — needs **{xp_needed}** more XP "
                f"to reach the realm cap (Level {get_realm(pet['level'])[3]})."
            )
            return

        realm_idx = get_realm_index(pet["level"])
        _, _, _, _, base_chance = REALMS[realm_idx]
        next_realm_name, next_realm_emoji, _, _, _ = REALMS[realm_idx + 1]
        current_realm_name, current_realm_emoji, _, _, _ = REALMS[realm_idx]

        # Vitality (avg of happiness/energy, minus hunger) nudges the odds —
        # rewards actually caring for the pet instead of just idling to cap.
        vitality_bonus = ((pet["happiness"] + pet["energy"]) / 2 - pet["hunger"]) / 400
        chance = max(0.05, min(0.95, base_chance + vitality_bonus))

        old_power = compute_power(pet)
        success = random.random() < chance

        if success:
            pet["level"] += 1
            pet["xp"] = 0
            # Breakthrough fully restores stats — the "reward" moment
            pet["hunger"] = 20
            pet["happiness"] = 100
            pet["energy"] = 100
            new_power = compute_power(pet)

            embed = discord.Embed(
                title=f"💥 BREAKTHROUGH SUCCESSFUL!",
                description=(
                    f"**{pet['name']}** shatters their limits and ascends from "
                    f"{current_realm_emoji} {current_realm_name} to "
                    f"**{next_realm_emoji} {next_realm_name}**!\n\n"
                    f"Power: `{old_power}` → `{new_power}` 🚀"
                ),
                color=0xFFD700,
                timestamp=datetime.now()
            )
        else:
            pet["breakthrough_fails"] += 1
            # Stumble: lose a chunk of XP, stay at cap, must regrind before retry
            setback = xp_to_next(pet["level"]) // 2
            pet["xp"] = max(0, pet["xp"] - setback)
            pet["happiness"] = max(0, pet["happiness"] - 15)

            embed = discord.Embed(
                title=f"⚠️ Breakthrough Failed...",
                description=(
                    f"**{pet['name']}** attempted to break into **{next_realm_name}** "
                    f"and faltered! The tribulation was too great.\n\n"
                    f"Lost some XP — grind back up and try again. "
                    f"(Attempt #{pet['breakthrough_fails']})"
                ),
                color=0x8B0000,
                timestamp=datetime.now()
            )
        embed.set_footer(text=f"Chance was {chance*100:.0f}%  •  EHKB Tech")
        self.save_pets()
        await interaction.response.send_message(embed=embed)

    # ── PVP ────────────────────────────────────────────────
    @app_commands.command(name="battle", description="Battle your pet against another member's pet")
    @app_commands.describe(opponent="Who to battle")
    async def battle(self, interaction: discord.Interaction, opponent: discord.Member):
        if opponent.id == interaction.user.id:
            await interaction.response.send_message("You can't battle yourself!")
            return
        if opponent.bot:
            await interaction.response.send_message("You can't battle a bot!")
            return

        attacker = self.get_pet(interaction.user.id, create_name=interaction.user.display_name)
        defender = self.get_pet(opponent.id, create_name=opponent.display_name)

        atk_power = compute_power(attacker)
        def_power = compute_power(defender)

        # Small random swing so it's not 100% deterministic, but power still dominates
        atk_roll = atk_power * random.uniform(0.85, 1.15)
        def_roll = def_power * random.uniform(0.85, 1.15)

        if atk_roll >= def_roll:
            winner, winner_pet, winner_user = interaction.user, attacker, interaction.user
            loser, loser_pet, loser_user = opponent, defender, opponent
        else:
            winner, winner_pet, winner_user = opponent, defender, opponent
            loser, loser_pet, loser_user = interaction.user, attacker, interaction.user

        winner_pet["wins"] += 1
        loser_pet["losses"] += 1
        win_events = self.add_xp(winner_pet, 30)
        lose_events = self.add_xp(loser_pet, 10)
        self.save_pets()

        realm_name, realm_emoji, _, _, _ = get_realm(winner_pet["level"])

        desc = (
            f"⚔️ **{attacker['name']}** ({atk_power} PWR) clashes with "
            f"**{defender['name']}** ({def_power} PWR)!\n\n"
            f"{realm_emoji} **{winner_pet['name']}** ({winner.mention}) wins! (+30 XP)\n"
            f"**{loser_pet['name']}** ({loser.mention}) puts up a fight. (+10 XP)"
        )
        if win_events:
            desc += "\n\n" + "\n".join(f"{winner_pet['name']}: {e}" for e in win_events)
        if lose_events:
            desc += "\n" + "\n".join(f"{loser_pet['name']}: {e}" for e in lose_events)

        embed = discord.Embed(
            title="Battle Result",
            description=desc,
            color=0x2b2d31,
            timestamp=datetime.now()
        )
        embed.set_footer(text="EHKB Tech")
        await interaction.response.send_message(embed=embed)

    # ── Leaderboard ──────────────────────────────────────
    @app_commands.command(name="petleaderboard", description="See the top pets")
    async def petleaderboard(self, interaction: discord.Interaction):
        if not self.pets:
            await interaction.response.send_message("No pets have been raised yet!")
            return

        ranked = sorted(
            self.pets.items(),
            key=lambda kv: (kv[1]["level"], kv[1]["xp"]),
            reverse=True
        )[:10]

        lines = []
        for i, (uid, pet) in enumerate(ranked, start=1):
            realm_name, realm_emoji, _, _, _ = get_realm(pet["level"])
            power = compute_power(pet)
            lines.append(
                f"**{i}.** {realm_emoji} **{pet['name']}** — {realm_name} Lv.{pet['level']} "
                f"(PWR {power}, {pet['wins']}W/{pet['losses']}L)"
            )

        embed = discord.Embed(
            title="🏆 Pet Leaderboard",
            description="\n".join(lines),
            color=0x2b2d31,
            timestamp=datetime.now()
        )
        embed.set_footer(text="EHKB Tech")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Pets(bot))
import os
import json
from dotenv import load_dotenv

load_dotenv()

# ── Discord ───────────────────────────────────────────
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_IDS = [int(x) for x in os.getenv("DISCORD_CHANNEL_IDS", "").split(",") if x]
DISCORD_ROLE_IDS = [int(x) for x in os.getenv("DISCORD_ROLE_IDS", "").split(",") if x]
COMMAND_CHANNEL_IDS = [int(x) for x in os.getenv("COMMAND_CHANNEL_IDS", "").split(",") if x]
ALLOWED_ROLE_IDS = [int(x) for x in os.getenv("ALLOWED_ROLE_IDS", "").split(",") if x]

# ── Roblox ────────────────────────────────────────────
ROBLOX_GAME_ID = int(os.getenv("ROBLOX_GAME_ID", "2210085102"))
ROBLOSECURITY_COOKIES = os.getenv("ROBLOSECURITY_COOKIES", "").split(",")
ROBLOSECURITY_COOKIES = [c.strip() for c in ROBLOSECURITY_COOKIES if c.strip()]

MEMBERS_FILE = os.getenv("MEMBERS_FILE", "BMMembers.txt")
FRIENDS_MAP_FILE = os.getenv("FRIENDS_MAP_FILE", "friends.json")
MASTER_MEMBERS_FILE = os.getenv("MASTER_MEMBERS_FILE", "MasterBMMembers.txt")

# ── Presence Loop ─────────────────────────────────────
PRESENCE_INTERVAL_MINUTES = int(os.getenv("PRESENCE_INTERVAL_MINUTES", "5"))
DEFAULT_ALERT_THRESHOLD = int(os.getenv("DEFAULT_ALERT_THRESHOLD", "4"))
DEFAULT_MIN_SERVER_POPULATION = int(os.getenv("DEFAULT_MIN_SERVER_POPULATION", "10"))

# ── Threshold Persistence ─────────────────────────────
SETTINGS_FILE = "settings.json"

def load_settings():
    """Returns (threshold, min_population) from file or defaults."""
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
            return (
                data.get("threshold", DEFAULT_ALERT_THRESHOLD),
                data.get("min_population", DEFAULT_MIN_SERVER_POPULATION)
            )
    except FileNotFoundError:
        return DEFAULT_ALERT_THRESHOLD, DEFAULT_MIN_SERVER_POPULATION

def save_settings(threshold, min_population):
    """Save current threshold and min_population to file."""
    with open(SETTINGS_FILE, "w") as f:
        json.dump({"threshold": threshold, "min_population": min_population}, f)

# Backward compatibility — keep old threshold functions
def load_threshold():
    return load_settings()[0]

def save_threshold(threshold):
    _, min_pop = load_settings()  # preserve existing min_pop when saving only threshold
    save_settings(threshold, min_pop)

# ── Friends Map Loading ──────────────────────────────
def load_friends_map():
    try:
        with open(FRIENDS_MAP_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
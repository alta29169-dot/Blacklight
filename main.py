import asyncio
import discord
from discord.ext import commands
import config
import aiohttp

intents = discord.Intents.default()
bot = commands.Bot(command_prefix=None, intents=intents)

async def verify_cookies():
    """Verify all configured cookies, print account info, and purge bad tokens."""
    print("\n" + "="*50)
    print("VERIFYING RELAY COOKIES")
    print("="*50)
    
    if not config.ROBLOSECURITY_COOKIES:
        print("[Main] No cookies configured in ROBLOSECURITY_COOKIES")
        return False
    
    valid_cookies = []
    url = "https://users.roblox.com/v1/users/authenticated"
    
    # Re-use a single session for all checks
    async with aiohttp.ClientSession() as session:
        for idx, cookie in enumerate(config.ROBLOSECURITY_COOKIES, 1):
            headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        user_id = data.get('id')
                        username = data.get('name')
                        print(f"[Main] Relay #{idx}: {username} (ID: {user_id})")
                        valid_cookies.append(cookie)
                    else:
                        print(f"[Main] Relay #{idx}: Invalid token (HTTP {resp.status})")
            except Exception as e:
                print(f"[Main] Relay #{idx}: Error - {str(e)}")
    
    print("="*50)
    print(f"Valid cookies: {len(valid_cookies)}/{len(config.ROBLOSECURITY_COOKIES)}")
    print("="*50 + "\n")
    
    if not valid_cookies:
        print("[Main] WARNING: No valid cookies found! Bot will not function properly.")
        return False
    
    # Overwrite config list in-place so cogs only receive valid cookies
    config.ROBLOSECURITY_COOKIES.clear()
    config.ROBLOSECURITY_COOKIES.extend(valid_cookies)
    
    return True

async def main():
    cookies_valid = await verify_cookies()
    if not cookies_valid:
        print("Aborting startup due to cookie verification failure.")
        return

    from cogs.events import Events
    from cogs.presence_loop import PresenceLoop
    from cogs.commands import Commands

    async with bot:
        await bot.add_cog(Events(bot))
        await bot.add_cog(PresenceLoop(bot))
        await bot.add_cog(Commands(bot))
        await bot.start(config.DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import discord
from discord.ext import commands
import config
import aiohttp

intents = discord.Intents.default()
bot = commands.Bot(command_prefix=None, intents=intents)

async def verify_cookies():
    """Verify all configured cookies and display their associated accounts."""
    print("\n" + "="*50)
    print("VERIFYING RELAY COOKIES")
    print("="*50)
    
    if not config.ROBLOSECURITY_COOKIES:
        print("❌ No cookies configured in ROBLOSECURITY_COOKIES")
        return False
    
    valid_cookies = []
    
    for idx, cookie in enumerate(config.ROBLOSECURITY_COOKIES, 1):
        try:
            async with aiohttp.ClientSession() as session:
                session.cookie_jar.update_cookies({'.ROBLOSECURITY': cookie})
                async with session.get('https://users.roblox.com/v1/me') as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        user_id = data['id']
                        username = data['name']
                        print(f"✅ Relay #{idx}: {username} (ID: {user_id})")
                        valid_cookies.append(cookie)
                    else:
                        print(f"❌ Relay #{idx}: Invalid token (HTTP {resp.status})")
        except Exception as e:
            print(f"❌ Relay #{idx}: Error - {str(e)}")
    
    print("="*50)
    print(f"Valid cookies: {len(valid_cookies)}/{len(config.ROBLOSECURITY_COOKIES)}")
    print("="*50 + "\n")
    
    if not valid_cookies:
        print("⚠️  WARNING: No valid cookies found! Bot will not function properly.")
        return False
    
    return True

async def main():
    # Verify cookies before starting
    cookies_valid = await verify_cookies()
    
    # Import cogs inside main to avoid circular issues (they use bot refs)
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
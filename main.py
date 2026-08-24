import asyncio
import discord
from discord.ext import commands
import config

intents = discord.Intents.default()
bot = commands.Bot(command_prefix=None, intents=intents)

async def main():
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
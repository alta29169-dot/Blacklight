from discord.ext import commands

class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Logged in as {self.bot.user}")
        # Sync commands to guild (optional, can be global)
        # GUILD = discord.Object(id=YOUR_GUILD_ID)
        # self.bot.tree.copy_global_to(guild=GUILD)
        # await self.bot.tree.sync(guild=GUILD)
        await self.bot.tree.sync()
        print("Command tree synced.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
import discord
from discord import app_commands
from config import ALLOWED_ROLE_IDS, COMMAND_CHANNEL_IDS

def has_allowed_role(interaction: discord.Interaction) -> bool:
    return any(
        discord.utils.get(interaction.user.roles, id=role_id) is not None
        for role_id in ALLOWED_ROLE_IDS
    )

def is_command_channel(interaction: discord.Interaction) -> bool:
    return interaction.channel_id in COMMAND_CHANNEL_IDS

def allowed_command():
    """Decorator to check channel and role permissions for commands."""
    async def predicate(interaction: discord.Interaction):
        if not is_command_channel(interaction):
            await interaction.response.send_message("Wrong channel.", ephemeral=True)
            return False
        if not has_allowed_role(interaction):
            await interaction.response.send_message("You don't have permission.", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)
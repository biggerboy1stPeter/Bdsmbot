import discord
from discord import app_commands
from discord.ext import commands
import os

class Basics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🏓 Pong! {round(self.bot.latency * 1000)}ms")

    @app_commands.command(name="safeword", description="Global safeword alert")
    async def safeword(self, interaction: discord.Interaction, reason: str = "No reason given"):
        # Get moderator role from database config
        mod_role_id = None
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM configs WHERE guild_id=$1 AND key='mod_role_id'",
                interaction.guild_id
            )
            if row:
                mod_role_id = row['value']
        mod_mention = f"<@&{mod_role_id}>" if mod_role_id else "Moderators"
        await interaction.response.send_message(
            f"🚨 **SAFECALL ACTIVATED** by {interaction.user.mention}\n"
            f"Reason: {reason}\n\n"
            f"{mod_mention} please respond immediately!"
        )

async def setup(bot):
    await bot.add_cog(Basics(bot))

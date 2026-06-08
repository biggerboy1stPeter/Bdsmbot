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
    @app_commands.guild_only()
    @app_commands.describe(reason="Optional reason for the safeword activation")
    async def safeword(self, interaction: discord.Interaction, reason: str = "No reason given"):
        mod_role_id = None
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM configs WHERE guild_id=$1 AND key='mod_role_id'",
                interaction.guild_id
            )
            if row:
                try:
                    mod_role_id = int(row['value'])
                except (ValueError, TypeError):
                    mod_role_id = None

        # Resolve role object (optional – for validation)
        role = None
        if mod_role_id:
            role = interaction.guild.get_role(mod_role_id)

        if role:
            mod_mention = role.mention
        else:
            mod_mention = "Moderators (no role configured)"

        await interaction.response.send_message(
            f"🚨 **SAFECALL ACTIVATED** by {interaction.user.mention}\n"
            f"Reason: {reason}\n\n"
            f"{mod_mention} please respond immediately!"
        )

async def setup(bot):
    await bot.add_cog(Basics(bot))
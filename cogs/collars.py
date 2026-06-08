import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

class Collars(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="collar", description="Collar a submissive (roleplay)")
    async def collar(self, interaction: discord.Interaction, sub: discord.Member):
        if sub == interaction.user:
            await interaction.response.send_message("You can't collar yourself silly~", ephemeral=True)
            return
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO collars (sub_id, dom_id, since) VALUES ($1, $2, NOW())
                ON CONFLICT (sub_id) DO UPDATE SET dom_id = $2, since = NOW()
            """, sub.id, interaction.user.id)
        await interaction.response.send_message(
            f"👑 **{interaction.user.mention} has collared {sub.mention}!** 🖤"
        )

    @app_commands.command(name="collarstatus", description="Check collar status")
    async def collarstatus(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT dom_id, since FROM collars WHERE sub_id = $1", member.id)
        if row:
            dom = self.bot.get_user(row['dom_id']) or "Unknown"
            since = row['since'].strftime("%d %b %Y") if row['since'] else "unknown"
            await interaction.response.send_message(f"⛓️ {member.mention} is collared by {dom} (since {since})")
        else:
            await interaction.response.send_message(f"{member.mention} is not currently collared.")

async def setup(bot):
    await bot.add_cog(Collars(bot))

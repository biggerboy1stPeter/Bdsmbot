import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import logging

logger = logging.getLogger("kinkbot")

class Collars(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="collar", description="Collar a submissive (roleplay)")
    @app_commands.guild_only()
    async def collar(self, interaction: discord.Interaction, sub: discord.Member):
        # Prevent self-collar
        if sub == interaction.user:
            await interaction.response.send_message("❌ You can't collar yourself, silly~", ephemeral=True)
            return

        # Prevent collaring bots
        if sub.bot:
            await interaction.response.send_message("❌ You cannot collar a bot.", ephemeral=True)
            return

        try:
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO collars (sub_id, dom_id, since) VALUES ($1, $2, NOW())
                    ON CONFLICT (sub_id) DO UPDATE SET dom_id = $2, since = NOW()
                """, sub.id, interaction.user.id)

            # Optional: log the action
            logger.info(f"{interaction.user} collared {sub} in guild {interaction.guild.name}")

            await interaction.response.send_message(
                f"👑 **{interaction.user.mention} has collared {sub.mention}!** 🖤"
            )
        except Exception as e:
            logger.error(f"Failed to collar {sub.id}: {e}")
            await interaction.response.send_message("❌ An error occurred while collaring.", ephemeral=True)

    @app_commands.command(name="uncollar", description="Release a submissive from their collar")
    @app_commands.guild_only()
    async def uncollar(self, interaction: discord.Interaction, sub: discord.Member):
        async with self.bot.db_pool.acquire() as conn:
            result = await conn.execute("DELETE FROM collars WHERE sub_id = $1", sub.id)
            if result == "DELETE 0":
                await interaction.response.send_message(f"{sub.mention} is not currently collared.", ephemeral=True)
                return
        await interaction.response.send_message(
            f"🔓 **{interaction.user.mention} has released {sub.mention} from their collar.**"
        )
        logger.info(f"{interaction.user} uncollared {sub} in guild {interaction.guild.name}")

    @app_commands.command(name="collarstatus", description="Check collar status")
    @app_commands.guild_only()
    async def collarstatus(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        try:
            async with self.bot.db_pool.acquire() as conn:
                row = await conn.fetchrow("SELECT dom_id, since FROM collars WHERE sub_id = $1", member.id)
        except Exception as e:
            logger.error(f"Failed to fetch collar status for {member.id}: {e}")
            await interaction.response.send_message("❌ Database error.", ephemeral=True)
            return

        if row:
            dom_id = row['dom_id']
            # Try to get dom from cache, else fetch from API
            dom = self.bot.get_user(dom_id)
            if not dom:
                try:
                    dom = await self.bot.fetch_user(dom_id)
                except:
                    dom = f"Unknown user ({dom_id})"
            since = row['since'].strftime("%d %b %Y") if row['since'] else "unknown"
            await interaction.response.send_message(
                f"⛓️ {member.mention} is collared by {dom} (since {since})"
            )
        else:
            await interaction.response.send_message(f"{member.mention} is not currently collared.")

async def setup(bot):
    await bot.add_cog(Collars(bot))
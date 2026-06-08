import os
import random
import logging
import discord
from discord.ext import commands, tasks

logger = logging.getLogger("kinkbot")

class AutoPost(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_tip.start()
        self.weekly_scene.start()

    def cog_unload(self):
        self.daily_tip.cancel()
        self.weekly_scene.cancel()

    # ------------------------------------------------------------------
    # Helper methods (defined before they are used)
    # ------------------------------------------------------------------
    async def get_setting(self, guild_id, key, default=None):
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM configs WHERE guild_id=$1 AND key=$2",
                guild_id, key
            )
            return row['value'] if row else default

    async def get_channel_by_setting(self, guild, key):
        channel_id_str = await self.get_setting(guild.id, key)
        if not channel_id_str:
            return None
        try:
            channel_id = int(channel_id_str)
        except ValueError:
            return None
        return guild.get_channel(channel_id)

    def get_random_image(self):
        """Return a path to a random image file (only common image extensions)."""
        image_dir = os.path.join(os.path.dirname(__file__), '..', 'images')
        if not os.path.isdir(image_dir):
            return None
        valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
        try:
            files = [f for f in os.listdir(image_dir)
                     if f.lower().endswith(valid_extensions)]
            if not files:
                return None
            chosen = random.choice(files)
            return os.path.join(image_dir, chosen)
        except Exception as e:
            logger.warning(f"Could not read images folder: {e}")
            return None

    # ------------------------------------------------------------------
    # Daily tip loop
    # ------------------------------------------------------------------
    @tasks.loop(hours=24)
    async def daily_tip(self):
        await self.bot.wait_until_ready()
        tips = [
            "💡 Always negotiate before a scene.",
            "💡 Aftercare is essential – cuddles, water, and talk.",
            "💡 Check in with your partner's emotional state regularly.",
            "💡 Safewords are not a sign of weakness but of trust.",
            "💡 Consent can be withdrawn at any time.",
        ]

        for guild in self.bot.guilds:
            try:
                # Check if enabled for this guild
                enabled = await self.get_setting(guild.id, "daily_tip_enabled", "true")
                if enabled != "true":
                    continue

                channel = await self.get_channel_by_setting(guild, "tips_channel")
                if not channel:
                    continue

                # Get a random image (optional)
                image_path = self.get_random_image()
                embed = discord.Embed(
                    title="🌟 Daily Kink Tip",
                    description=random.choice(tips),
                    color=0xdc2626
                )
                embed.set_footer(text="BDSM Collective • Stay safe, stay kinky")

                file = None
                if image_path:
                    file = discord.File(image_path, filename=os.path.basename(image_path))
                    embed.set_image(url=f"attachment://{os.path.basename(image_path)}")

                await channel.send(embed=embed, file=file)
                logger.info(f"Daily tip sent to {guild.name} / #{channel.name}")

            except discord.Forbidden:
                logger.warning(f"No permission to send daily tip in {guild.name} (channel {channel.name if channel else 'unknown'})")
            except discord.HTTPException as e:
                logger.error(f"HTTP error sending daily tip in {guild.name}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in daily tip for {guild.name}: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Weekly scene loop
    # ------------------------------------------------------------------
    @tasks.loop(hours=168)  # 7 days
    async def weekly_scene(self):
        await self.bot.wait_until_ready()
        scenes = [
            "🎭 **Scene Idea:** Sensory deprivation – blindfold, headphones, and feather touch.",
            "🎭 **Scene Idea:** Predator/prey – hide and seek in a safe space.",
            "🎭 **Scene Idea:** Service sub day – serve your Dom/me breakfast in bed.",
        ]

        for guild in self.bot.guilds:
            try:
                channel = await self.get_channel_by_setting(guild, "scenes_channel")
                if not channel:
                    continue

                image_path = self.get_random_image()
                embed = discord.Embed(
                    title="📋 Weekly Scene Prompt",
                    description=random.choice(scenes),
                    color=0xdc2626
                )
                embed.set_footer(text="BDSM Collective • Play responsibly")

                file = None
                if image_path:
                    file = discord.File(image_path, filename=os.path.basename(image_path))
                    embed.set_image(url=f"attachment://{os.path.basename(image_path)}")

                await channel.send(embed=embed, file=file)
                logger.info(f"Weekly scene sent to {guild.name} / #{channel.name}")

            except discord.Forbidden:
                logger.warning(f"No permission to send weekly scene in {guild.name}")
            except discord.HTTPException as e:
                logger.error(f"HTTP error sending weekly scene in {guild.name}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in weekly scene for {guild.name}: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Loop startup delay
    # ------------------------------------------------------------------
    @daily_tip.before_loop
    @weekly_scene.before_loop
    async def before_loops(self):
        await self.bot.wait_until_ready()
        # Stagger the first run to avoid hitting Discord at the same second
        await asyncio.sleep(10)

async def setup(bot):
    await bot.add_cog(AutoPost(bot))

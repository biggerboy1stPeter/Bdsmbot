import discord
from discord.ext import commands, tasks
import os
import random

class AutoPost(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_tip.start()
        self.weekly_scene.start()

    def cog_unload(self):
        self.daily_tip.cancel()
        self.weekly_scene.cancel()

    def get_random_image(self, folder="."):
        # Images are stored in the bot's /images folder
        image_dir = os.path.join(os.path.dirname(__file__), '..', 'images')
        try:
            files = os.listdir(image_dir)
            if files:
                return os.path.join(image_dir, random.choice(files))
        except Exception:
            pass
        return None

    async def get_channel_by_setting(self, guild, key):
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM configs WHERE guild_id=$1 AND key=$2", guild.id, key)
        if row:
            return guild.get_channel(int(row['value']))
        return None

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
            channel = await self.get_channel_by_setting(guild, "tips_channel")
            if not channel:
                continue
            enabled = await self.get_setting(guild.id, "daily_tip_enabled", "true")
            if enabled != "true":
                continue
            image_path = self.get_random_image()
            embed = discord.Embed(title="🌟 Daily Kink Tip", description=random.choice(tips), color=0xdc2626)
            embed.set_footer(text="BDSM Collective • Stay safe, stay kinky")
            file = None
            if image_path:
                file = discord.File(image_path, filename=os.path.basename(image_path))
                embed.set_image(url=f"attachment://{os.path.basename(image_path)}")
            await channel.send(file=file, embed=embed)

    @tasks.loop(hours=168)  # weekly
    async def weekly_scene(self):
        await self.bot.wait_until_ready()
        scenes = [
            "🎭 **Scene Idea:** Sensory deprivation – blindfold, headphones, and feather touch.",
            "🎭 **Scene Idea:** Predator/prey – hide and seek in a safe space.",
            "🎭 **Scene Idea:** Service sub day – serve your Dom/me breakfast in bed.",
        ]
        for guild in self.bot.guilds:
            channel = await self.get_channel_by_setting(guild, "scenes_channel")
            if not channel:
                continue
            image_path = self.get_random_image()
            embed = discord.Embed(title="📋 Weekly Scene Prompt", description=random.choice(scenes), color=0xdc2626)
            embed.set_footer(text="BDSM Collective • Play responsibly")
            file = None
            if image_path:
                file = discord.File(image_path, filename=os.path.basename(image_path))
                embed.set_image(url=f"attachment://{os.path.basename(image_path)}")
            await channel.send(file=file, embed=embed)

    async def get_setting(self, guild_id, key, default=None):
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM configs WHERE guild_id=$1 AND key=$2", guild_id, key)
            return row['value'] if row else default

    @daily_tip.before_loop
    @weekly_scene.before_loop
    async def before_loops(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(AutoPost(bot))

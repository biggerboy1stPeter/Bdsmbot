import os
import json
import random
import asyncio
import logging
from datetime import datetime, timedelta, time

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
    # Helpers
    # ------------------------------------------------------------------
    async def get_setting(self, guild_id, key, default=None):
        """Fetch a string value from configs table. Returns default on error."""
        try:
            async with self.bot.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT value FROM configs WHERE guild_id=$1 AND key=$2",
                    guild_id, key
                )
                return row['value'] if row else default
        except Exception as e:
            logger.error(f"DB error fetching {key} for guild {guild_id}: {e}")
            return default

    async def get_setting_json(self, guild_id, key, default=None):
        """Fetch and parse a JSON array from configs. Returns default on error."""
        val = await self.get_setting(guild_id, key)
        if val is None:
            return default
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Invalid JSON for {key} in guild {guild_id}")
            return default

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
        """Return path to a random image from the images folder."""
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

    async def _send_embed(self, channel, title, description, color=0xDC2626,
                          footer="BDSM Collective • Stay safe, stay kinky",
                          mention_role=None):
        """Send a single embed (with optional image and role mention)."""
        image_path = self.get_random_image()
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text=footer)

        file = None
        if image_path:
            file = discord.File(image_path, filename=os.path.basename(image_path))
            embed.set_image(url=f"attachment://{os.path.basename(image_path)}")

        # Build content (mention) if any
        content = None
        if mention_role and channel.guild:
            role = channel.guild.get_role(mention_role)
            if role:
                content = role.mention

        await channel.send(content=content, embed=embed, file=file)

    # ------------------------------------------------------------------
    # Time scheduling helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_time(time_str):
        """Parse 'HH:MM' string into a time object. Returns None if invalid."""
        try:
            hour, minute = map(int, time_str.split(':'))
            return time(hour, minute)
        except Exception:
            return None

    @staticmethod
    def _parse_weekday_time(day_time_str):
        """
        Parse 'Monday 09:00', 'tue 18:30', etc.
        Returns (weekday_int, time) or (None, None) on failure.
        """
        days = ['monday', 'tuesday', 'wednesday', 'thursday',
                'friday', 'saturday', 'sunday']
        parts = day_time_str.strip().split()
        if len(parts) != 2:
            return None, None
        day_name = parts[0].lower()
        if day_name not in days:
            # support abbreviated
            for i, d in enumerate(days):
                if d.startswith(day_name):
                    day_name = d
                    break
            else:
                return None, None
        weekday = days.index(day_name)
        t = AutoPost._parse_time(parts[1])
        if t is None:
            return None, None
        return weekday, t

    async def _get_next_run_datetime(self, guild, prefix, default_time,
                                     is_weekly=False):
        """
        Calculate the datetime of the next scheduled run for a task.
        prefix: setting key prefix, e.g. 'daily_tip_time' or 'weekly_scene_time'
        default_time: default time object to use if not set
        is_weekly: True if the task runs once a week
        """
        now = datetime.utcnow()
        if is_weekly:
            raw = await self.get_setting(guild.id, f"{prefix}", None)
            if raw:
                weekday, target_time = self._parse_weekday_time(raw)
            else:
                # default: Monday 12:00
                target_time = default_time or time(12, 0)
                weekday = 0  # Monday
            if target_time is None:
                target_time = default_time or time(12, 0)

            # Calculate next occurrence
            next_run = now.replace(hour=target_time.hour,
                                   minute=target_time.minute,
                                   second=0, microsecond=0)
            days_ahead = weekday - next_run.weekday()
            if days_ahead < 0:
                days_ahead += 7
            elif days_ahead == 0 and next_run <= now:
                days_ahead = 7
            next_run += timedelta(days=days_ahead)
            return next_run
        else:
            # daily
            raw = await self.get_setting(guild.id, f"{prefix}", None)
            if raw:
                target_time = self._parse_time(raw) or default_time
            else:
                target_time = default_time or time(12, 0)

            next_run = now.replace(hour=target_time.hour,
                                   minute=target_time.minute,
                                   second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run

    # ------------------------------------------------------------------
    # Loops (now using before_loop to wait for scheduled time)
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
                enabled = await self.get_setting(guild.id, "daily_tip_enabled", "true")
                if enabled != "true":
                    continue
                channel = await self.get_channel_by_setting(guild, "tips_channel")
                if not channel:
                    continue

                # Custom tips (merge with defaults)
                custom_tips = await self.get_setting_json(guild.id, "custom_tips", [])
                all_tips = tips + custom_tips if custom_tips else tips

                # Custom color
                color = await self.get_setting(guild.id, "embed_color", None)
                color = int(color, 16) if color else 0xDC2626

                # Mention role
                mention_role_id = await self.get_setting(guild.id, "mention_role_id", None)
                if mention_role_id:
                    mention_role_id = int(mention_role_id) if mention_role_id.isdigit() else None

                await self._send_embed(
                    channel,
                    "🌟 Daily Kink Tip",
                    random.choice(all_tips),
                    color=color,
                    mention_role=mention_role_id
                )
                logger.info(f"Daily tip sent to {guild.name} / #{channel.name}")

            except discord.Forbidden:
                logger.warning(f"No permission in {guild.name} (#{channel.name if channel else 'unknown'})")
            except discord.HTTPException as e:
                logger.error(f"HTTP error in {guild.name}: {e}")
            except Exception:
                logger.exception(f"Unexpected error in daily tip for {guild.name}")

    @tasks.loop(hours=168)  # 7 days
    async def weekly_scene(self):
        await self.bot.wait_until_ready()
        default_scenes = [
            "🎭 **Scene Idea:** Sensory deprivation – blindfold, headphones, and feather touch.",
            "🎭 **Scene Idea:** Predator/prey – hide and seek in a safe space.",
            "🎭 **Scene Idea:** Service sub day – serve your Dom/me breakfast in bed.",
        ]

        for guild in self.bot.guilds:
            try:
                enabled = await self.get_setting(guild.id, "weekly_scene_enabled", "true")
                if enabled != "true":
                    continue
                channel = await self.get_channel_by_setting(guild, "scenes_channel")
                if not channel:
                    continue

                custom_scenes = await self.get_setting_json(guild.id, "custom_scenes", [])
                all_scenes = default_scenes + custom_scenes if custom_scenes else default_scenes

                color = await self.get_setting(guild.id, "embed_color", None)
                color = int(color, 16) if color else 0xDC2626

                mention_role_id = await self.get_setting(guild.id, "mention_role_id", None)
                if mention_role_id:
                    mention_role_id = int(mention_role_id) if mention_role_id.isdigit() else None

                await self._send_embed(
                    channel,
                    "📋 Weekly Scene Prompt",
                    random.choice(all_scenes),
                    color=color,
                    footer="BDSM Collective • Play responsibly",
                    mention_role=mention_role_id
                )
                logger.info(f"Weekly scene sent to {guild.name} / #{channel.name}")

            except discord.Forbidden:
                logger.warning(f"No permission in {guild.name} (#{channel.name if channel else 'unknown'})")
            except discord.HTTPException as e:
                logger.error(f"HTTP error in {guild.name}: {e}")
            except Exception:
                logger.exception(f"Unexpected error in weekly scene for {guild.name}")

    # ------------------------------------------------------------------
    # Before loop: wait until the next scheduled time
    # ------------------------------------------------------------------
    @daily_tip.before_loop
    async def before_daily_tip(self):
        await self.bot.wait_until_ready()
        # We compute the wait for the first guild (the loop starts once, then posts to all)
        # The scheduler is per-guild, but for simplicity we align to the earliest next run
        # More robust: just use the first available guild's time, or a hard default.
        # Here we use a default 12:00 UTC if no guild is available yet.
        now = datetime.utcnow()
        target = now.replace(hour=12, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)

        if self.bot.guilds:
            # Use the first guild that has a daily tip time set
            guild = self.bot.guilds[0]
            target = await self._get_next_run_datetime(guild, "daily_tip_time", time(12, 0))
        wait = (target - datetime.utcnow()).total_seconds()
        if wait > 0:
            logger.info(f"Daily tip first run in {wait/3600:.1f} hours")
            await asyncio.sleep(wait)

    @weekly_scene.before_loop
    async def before_weekly_scene(self):
        await self.bot.wait_until_ready()
        now = datetime.utcnow()
        # Default: next Monday 12:00
        target = now.replace(hour=12, minute=0, second=0, microsecond=0)
        days_ahead = 0 - target.weekday()  # Monday = 0
        if days_ahead < 0:
            days_ahead += 7
        elif days_ahead == 0 and target <= now:
            days_ahead = 7
        target += timedelta(days=days_ahead)

        if self.bot.guilds:
            guild = self.bot.guilds[0]
            target = await self._get_next_run_datetime(guild, "weekly_scene_time", time(12, 0), is_weekly=True)
        wait = (target - datetime.utcnow()).total_seconds()
        if wait > 0:
            logger.info(f"Weekly scene first run in {wait/3600:.1f} hours")
            await asyncio.sleep(wait)

    # ------------------------------------------------------------------
    # Admin commands
    # ------------------------------------------------------------------
    def _admin_only():
        async def predicate(ctx):
            return ctx.author.guild_permissions.manage_guild
        return commands.check(predicate)

    @commands.group(name="autopost", invoke_without_command=True)
    @_admin_only()
    async def autopost_group(self, ctx):
        """Manage automatic posting settings."""
        await ctx.send_help(ctx.command)

    # --- Custom tips management ---
    @autopost_group.group(name="tips", invoke_without_command=True)
    async def tips_group(self, ctx):
        await ctx.send_help(ctx.command)

    @tips_group.command(name="add")
    async def add_tip(self, ctx, *, tip: str):
        """Add a custom daily tip to this server's rotation."""
        tips = await self.get_setting_json(ctx.guild.id, "custom_tips", [])
        tips.append(tip)
        await self._save_json(ctx.guild.id, "custom_tips", tips)
        await ctx.send(f"✅ Added tip. You now have {len(tips)} custom tip(s).")

    @tips_group.command(name="remove")
    async def remove_tip(self, ctx, index: int):
        """Remove a custom tip by its number (see list)."""
        tips = await self.get_setting_json(ctx.guild.id, "custom_tips", [])
        if not tips:
            return await ctx.send("No custom tips to remove.")
        if index < 1 or index > len(tips):
            return await ctx.send(f"❌ Index must be between 1 and {len(tips)}.")
        removed = tips.pop(index - 1)
        await self._save_json(ctx.guild.id, "custom_tips", tips)
        await ctx.send(f"🗑️ Removed: {removed}")

    @tips_group.command(name="list")
    async def list_tips(self, ctx):
        """Show all custom tips for this server."""
        tips = await self.get_setting_json(ctx.guild.id, "custom_tips", [])
        if not tips:
            return await ctx.send("No custom tips yet.")
        msg = "\n".join(f"{i+1}. {t}" for i, t in enumerate(tips))
        await ctx.send(f"**Custom Tips:**\n{msg}")

    # --- Custom scenes management ---
    @autopost_group.group(name="scenes", invoke_without_command=True)
    async def scenes_group(self, ctx):
        await ctx.send_help(ctx.command)

    @scenes_group.command(name="add")
    async def add_scene(self, ctx, *, scene: str):
        """Add a custom weekly scene prompt."""
        scenes = await self.get_setting_json(ctx.guild.id, "custom_scenes", [])
        scenes.append(scene)
        await self._save_json(ctx.guild.id, "custom_scenes", scenes)
        await ctx.send(f"✅ Added scene. You now have {len(scenes)} custom scene(s).")

    @scenes_group.command(name="remove")
    async def remove_scene(self, ctx, index: int):
        scenes = await self.get_setting_json(ctx.guild.id, "custom_scenes", [])
        if not scenes:
            return await ctx.send("No custom scenes to remove.")
        if index < 1 or index > len(scenes):
            return await ctx.send(f"❌ Index must be between 1 and {len(scenes)}.")
        removed = scenes.pop(index - 1)
        await self._save_json(ctx.guild.id, "custom_scenes", scenes)
        await ctx.send(f"🗑️ Removed: {removed}")

    @scenes_group.command(name="list")
    async def list_scenes(self, ctx):
        scenes = await self.get_setting_json(ctx.guild.id, "custom_scenes", [])
        if not scenes:
            return await ctx.send("No custom scenes yet.")
        msg = "\n".join(f"{i+1}. {s}" for i, s in enumerate(scenes))
        await ctx.send(f"**Custom Scenes:**\n{msg}")

    # --- Scheduling ---
    @autopost_group.command(name="setdaily")
    async def set_daily_time(self, ctx, time_str: str):
        """Set the daily tip time (HH:MM UTC). Example: 09:30"""
        t = self._parse_time(time_str)
        if not t:
            return await ctx.send("❌ Invalid time format. Use HH:MM (24h).")
        await self._save_config(ctx.guild.id, "daily_tip_time", time_str)
        await ctx.send(f"✅ Daily tip time set to {time_str} UTC (takes effect on next loop restart).")

    @autopost_group.command(name="setweekly")
    async def set_weekly_time(self, ctx, *, day_time: str):
        """Set the weekly scene day & time. Example: Monday 18:00"""
        weekday, t = self._parse_weekday_time(day_time)
        if weekday is None:
            return await ctx.send("❌ Invalid format. Use e.g. 'Monday 18:00'.")
        await self._save_config(ctx.guild.id, "weekly_scene_time", day_time)
        await ctx.send(f"✅ Weekly scene time set to {day_time} UTC (takes effect on next loop restart).")

    # --- Misc settings ---
    @autopost_group.command(name="color")
    async def set_color(self, ctx, hex_color: str):
        """Set the embed color (hex). Example: ff9900"""
        hex_color = hex_color.lstrip('#')
        try:
            int(hex_color, 16)
        except ValueError:
            return await ctx.send("❌ Invalid hex color.")
        await self._save_config(ctx.guild.id, "embed_color", hex_color)
        await ctx.send(f"✅ Embed color set to #{hex_color}.")

    @autopost_group.command(name="mention")
    async def set_mention(self, ctx, role: discord.Role):
        """Set a role to mention before each post."""
        await self._save_config(ctx.guild.id, "mention_role_id", str(role.id))
        await ctx.send(f"✅ Will mention {role.mention} before posts.")

    @autopost_group.command(name="testpost")
    async def test_post(self, ctx, post_type: str):
        """Manually trigger a daily or weekly post (admin only).
        Usage: !autopost testpost daily  or  !autopost testpost weekly
        """
        if post_type.lower() not in ("daily", "weekly"):
            return await ctx.send("Specify 'daily' or 'weekly'.")
        if post_type.lower() == "daily":
            # manual run of daily logic for this guild only
            enabled = await self.get_setting(ctx.guild.id, "daily_tip_enabled", "true")
            if enabled != "true":
                return await ctx.send("Daily tips are disabled for this server.")
            channel = await self.get_channel_by_setting(ctx.guild, "tips_channel")
            if not channel:
                return await ctx.send("No tips channel configured.")
            tips = [
                "💡 Always negotiate before a scene.",
                "💡 Aftercare is essential – cuddles, water, and talk.",
                "💡 Check in with your partner's emotional state regularly.",
                "💡 Safewords are not a sign of weakness but of trust.",
                "💡 Consent can be withdrawn at any time.",
            ]
            custom_tips = await self.get_setting_json(ctx.guild.id, "custom_tips", [])
            all_tips = tips + custom_tips if custom_tips else tips
            color = await self.get_setting(ctx.guild.id, "embed_color", None)
            color = int(color, 16) if color else 0xDC2626
            mention_role_id = await self.get_setting(ctx.guild.id, "mention_role_id", None)
            if mention_role_id:
                mention_role_id = int(mention_role_id) if mention_role_id.isdigit() else None
            await self._send_embed(channel, "🌟 Daily Kink Tip (Test)",
                                   random.choice(all_tips), color=color,
                                   mention_role=mention_role_id)
            await ctx.send("✅ Test daily tip sent.")
        else:
            enabled = await self.get_setting(ctx.guild.id, "weekly_scene_enabled", "true")
            if enabled != "true":
                return await ctx.send("Weekly scenes are disabled for this server.")
            channel = await self.get_channel_by_setting(ctx.guild, "scenes_channel")
            if not channel:
                return await ctx.send("No scenes channel configured.")
            default_scenes = [
                "🎭 **Scene Idea:** Sensory deprivation – blindfold, headphones, and feather touch.",
                "🎭 **Scene Idea:** Predator/prey – hide and seek in a safe space.",
                "🎭 **Scene Idea:** Service sub day – serve your Dom/me breakfast in bed.",
            ]
            custom_scenes = await self.get_setting_json(ctx.guild.id, "custom_scenes", [])
            all_scenes = default_scenes + custom_scenes if custom_scenes else default_scenes
            color = await self.get_setting(ctx.guild.id, "embed_color", None)
            color = int(color, 16) if color else 0xDC2626
            mention_role_id = await self.get_setting(ctx.guild.id, "mention_role_id", None)
            if mention_role_id:
                mention_role_id = int(mention_role_id) if mention_role_id.isdigit() else None
            await self._send_embed(channel, "📋 Weekly Scene Prompt (Test)",
                                   random.choice(all_scenes), color=color,
                                   footer="BDSM Collective • Play responsibly",
                                   mention_role=mention_role_id)
            await ctx.send("✅ Test weekly scene sent.")

    # ------------------------------------------------------------------
    # Internal save helpers
    # ------------------------------------------------------------------
    async def _save_config(self, guild_id, key, value):
        """Upsert a simple key/value config."""
        try:
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO configs (guild_id, key, value)
                       VALUES ($1, $2, $3)
                       ON CONFLICT (guild_id, key)
                       DO UPDATE SET value = EXCLUDED.value""",
                    guild_id, key, value
                )
        except Exception as e:
            logger.error(f"Failed to save config {key} for guild {guild_id}: {e}")

    async def _save_json(self, guild_id, key, data):
        """Save a Python object as JSON string."""
        await self._save_config(guild_id, key, json.dumps(data))


async def setup(bot):
    await bot.add_cog(AutoPost(bot))
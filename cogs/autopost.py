import os
import re
import json
import random
import asyncio
import logging
import discord
from discord.ext import commands, tasks

# Shared UI classes (must exist in cogs/base_view.py)
from cogs.base_view import BaseConfigView, ChannelSelectView, RoleSelectView

logger = logging.getLogger("kinkbot")

# ------------------------------------------------------------------
# Temporary MainMenu replacement to avoid circular import.
# Replace this with the real MainMenu once you move it to base_view.py.
# ------------------------------------------------------------------
class MainMenu(BaseConfigView):
    def __init__(self, bot, guild_id):
        super().__init__(bot, guild_id, timeout=600)
    @discord.ui.button(label="Use /admin to reopen panel", style=discord.ButtonStyle.secondary, disabled=True)
    async def dummy(self, interaction, button):
        pass

# ------------------------------------------------------------------
# AutoPost Menu (Full Settings)
# ------------------------------------------------------------------
class AutoPostMenu(BaseConfigView):
    def __init__(self, bot, guild_id):
        super().__init__(bot, guild_id, timeout=600)
        self._init_states = asyncio.create_task(self._fetch_states())

    async def _fetch_states(self):
        daily_enabled = await self.get_setting("daily_tip_enabled", "true")
        self.toggle_daily.label = "Daily Tip: ON" if daily_enabled == "true" else "Daily Tip: OFF"
        self.toggle_daily.style = discord.ButtonStyle.success if daily_enabled == "true" else discord.ButtonStyle.danger

        weekly_enabled = await self.get_setting("weekly_scene_enabled", "true")
        self.toggle_weekly.label = "Weekly Scene: ON" if weekly_enabled == "true" else "Weekly Scene: OFF"
        self.toggle_weekly.style = discord.ButtonStyle.success if weekly_enabled == "true" else discord.ButtonStyle.danger

    @discord.ui.button(label="Set Tips Channel", style=discord.ButtonStyle.success, emoji="#️⃣")
    async def tips_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChannelSelectView(self.bot, self.guild_id, "tips_channel", parent_menu=self)
        await interaction.response.edit_message(content="Select a channel for daily tips:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Set Scenes Channel", style=discord.ButtonStyle.success, emoji="#️⃣")
    async def scenes_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChannelSelectView(self.bot, self.guild_id, "scenes_channel", parent_menu=self)
        await interaction.response.edit_message(content="Select a channel for weekly scene ideas:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Daily Tip: ON", style=discord.ButtonStyle.success, emoji="✅", row=1)
    async def toggle_daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = await self.get_setting("daily_tip_enabled", "true")
        new = "false" if current == "true" else "true"
        await self.set_setting("daily_tip_enabled", new)
        button.label = "Daily Tip: ON" if new == "true" else "Daily Tip: OFF"
        button.style = discord.ButtonStyle.success if new == "true" else discord.ButtonStyle.danger
        await interaction.response.edit_message(view=self)
        self.message = await interaction.original_response()

    @discord.ui.button(label="Weekly Scene: ON", style=discord.ButtonStyle.success, emoji="✅", row=1)
    async def toggle_weekly(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = await self.get_setting("weekly_scene_enabled", "true")
        new = "false" if current == "true" else "true"
        await self.set_setting("weekly_scene_enabled", new)
        button.label = "Weekly Scene: ON" if new == "true" else "Weekly Scene: OFF"
        button.style = discord.ButtonStyle.success if new == "true" else discord.ButtonStyle.danger
        await interaction.response.edit_message(view=self)
        self.message = await interaction.original_response()

    @discord.ui.button(label="Daily Time", style=discord.ButtonStyle.primary, emoji="🕐", row=2)
    async def set_daily_time(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = await self.get_setting("daily_tip_time", "12:00")
        modal = SetTimeModal("daily_tip_time", current, self.bot, self.guild_id, parent_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Weekly Time", style=discord.ButtonStyle.primary, emoji="🕒", row=2)
    async def set_weekly_time(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = await self.get_setting("weekly_scene_time", "Monday 12:00")
        modal = SetTimeModal("weekly_scene_time", current, self.bot, self.guild_id, parent_view=self, weekly=True)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Embed Colour", style=discord.ButtonStyle.primary, emoji="🎨", row=2)
    async def set_colour(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = await self.get_setting("embed_color", "dc2626")
        modal = SetColourModal(self.bot, self.guild_id, current, parent_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Mention Role", style=discord.ButtonStyle.success, emoji="📢", row=3)
    async def mention_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RoleSelectView(self.bot, self.guild_id, "mention_role_id", parent_menu=self)
        await interaction.response.edit_message(content="Select a role to mention before each post:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Manage Custom Tips", style=discord.ButtonStyle.secondary, emoji="💬", row=4)
    async def custom_tips(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CustomTipsMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Custom Tips**", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Manage Custom Scenes", style=discord.ButtonStyle.secondary, emoji="🎭", row=4)
    async def custom_scenes(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CustomScenesMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Custom Scene Prompts**", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Test Daily Post", style=discord.ButtonStyle.gray, emoji="🚀", row=5)
    async def test_daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._test_post(interaction, "daily")

    @discord.ui.button(label="Test Weekly Post", style=discord.ButtonStyle.gray, emoji="🚀", row=5)
    async def test_weekly(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._test_post(interaction, "weekly")

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, row=5)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Uses the temporary MainMenu defined in this file.
        view = MainMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Admin Panel**", view=view)
        view.message = await interaction.original_response()

    async def _test_post(self, interaction, post_type):
        await interaction.response.defer(ephemeral=True)

        if post_type == "daily":
            enabled = await self.get_setting("daily_tip_enabled", "true")
            channel_key = "tips_channel"
            title = "🌟 Daily Kink Tip (Test)"
            default_prompts = [
                "💡 Always negotiate before a scene.",
                "💡 Aftercare is essential – cuddles, water, and talk.",
                "💡 Check in with your partner's emotional state regularly.",
                "💡 Safewords are not a sign of weakness but of trust.",
                "💡 Consent can be withdrawn at any time.",
            ]
            custom_key = "custom_tips"
        else:
            enabled = await self.get_setting("weekly_scene_enabled", "true")
            channel_key = "scenes_channel"
            title = "📋 Weekly Scene Prompt (Test)"
            default_prompts = [
                "🎭 **Scene Idea:** Sensory deprivation – blindfold, headphones, and feather touch.",
                "🎭 **Scene Idea:** Predator/prey – hide and seek in a safe space.",
                "🎭 **Scene Idea:** Service sub day – serve your Dom/me breakfast in bed.",
            ]
            custom_key = "custom_scenes"

        if enabled != "true":
            return await interaction.followup.send("❌ This feature is disabled.", ephemeral=True)

        channel_id_str = await self.get_setting(channel_key)
        if not channel_id_str:
            return await interaction.followup.send("❌ No channel configured.", ephemeral=True)
        channel = interaction.guild.get_channel(int(channel_id_str))
        if not channel:
            return await interaction.followup.send("❌ Configured channel not found.", ephemeral=True)

        custom_list = await self._get_json_setting(custom_key, [])
        all_prompts = default_prompts + custom_list if custom_list else default_prompts
        prompt = random.choice(all_prompts)

        color = await self.get_setting("embed_color", "dc2626")
        color_int = int(color, 16) if color else 0xDC2626
        mention_role_id = await self.get_setting("mention_role_id", None)
        mention_role_id = int(mention_role_id) if mention_role_id else None

        await self._send_embed_to_channel(channel, title, prompt, color_int, mention_role_id)
        await interaction.followup.send(f"✅ Test {post_type} post sent to {channel.mention}", ephemeral=True)

    async def _get_json_setting(self, key, default=None):
        val = await self.get_setting(key)
        if val is None:
            return default
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default

    async def _send_embed_to_channel(self, channel, title, description, color, mention_role_id):
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text="BDSM Collective • Stay safe, stay kinky")
        content = None
        if mention_role_id:
            role = channel.guild.get_role(mention_role_id)
            if role:
                content = role.mention
        await channel.send(content=content, embed=embed)

# ------------------------------------------------------------------
# Custom Tips / Scenes Sub‑Menus
# ------------------------------------------------------------------
class CustomTipsMenu(BaseConfigView):
    def __init__(self, bot, guild_id):
        super().__init__(bot, guild_id, timeout=300)

    @discord.ui.button(label="Add Tip", style=discord.ButtonStyle.success, emoji="➕")
    async def add_tip(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddTextModal("custom_tips", "tip", self.bot, self.guild_id, parent_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove Tip", style=discord.ButtonStyle.danger, emoji="➖")
    async def remove_tip(self, interaction: discord.Interaction, button: discord.ui.Button):
        tips = await self._get_tips()
        if not tips:
            await interaction.response.send_message("No custom tips to remove.", ephemeral=True)
            return
        view = RemoveItemView(self.bot, self.guild_id, "custom_tips", tips, parent_menu=self)
        await interaction.response.edit_message(content="Select a tip to remove:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="List Tips", style=discord.ButtonStyle.secondary, emoji="📋")
    async def list_tips(self, interaction: discord.Interaction, button: discord.ui.Button):
        tips = await self._get_tips()
        if not tips:
            await interaction.response.send_message("No custom tips yet.", ephemeral=True)
            return
        msg = "\n".join(f"{i+1}. {t}" for i, t in enumerate(tips))
        await interaction.response.send_message(f"**Custom Tips:**\n{msg}", ephemeral=True)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AutoPostMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Auto-Post Settings**", view=view)
        view.message = await interaction.original_response()

    async def _get_tips(self):
        val = await self.get_setting("custom_tips")
        if not val:
            return []
        try:
            return json.loads(val)
        except:
            return []

class CustomScenesMenu(BaseConfigView):
    def __init__(self, bot, guild_id):
        super().__init__(bot, guild_id, timeout=300)

    @discord.ui.button(label="Add Scene", style=discord.ButtonStyle.success, emoji="➕")
    async def add_scene(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddTextModal("custom_scenes", "scene", self.bot, self.guild_id, parent_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove Scene", style=discord.ButtonStyle.danger, emoji="➖")
    async def remove_scene(self, interaction: discord.Interaction, button: discord.ui.Button):
        scenes = await self._get_scenes()
        if not scenes:
            await interaction.response.send_message("No custom scenes to remove.", ephemeral=True)
            return
        view = RemoveItemView(self.bot, self.guild_id, "custom_scenes", scenes, parent_menu=self)
        await interaction.response.edit_message(content="Select a scene to remove:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="List Scenes", style=discord.ButtonStyle.secondary, emoji="📋")
    async def list_scenes(self, interaction: discord.Interaction, button: discord.ui.Button):
        scenes = await self._get_scenes()
        if not scenes:
            await interaction.response.send_message("No custom scenes yet.", ephemeral=True)
            return
        msg = "\n".join(f"{i+1}. {s}" for i, s in enumerate(scenes))
        await interaction.response.send_message(f"**Custom Scene Prompts:**\n{msg}", ephemeral=True)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AutoPostMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Auto-Post Settings**", view=view)
        view.message = await interaction.original_response()

    async def _get_scenes(self):
        val = await self.get_setting("custom_scenes")
        if not val:
            return []
        try:
            return json.loads(val)
        except:
            return []

# ------------------------------------------------------------------
# Shared Modals & Views
# ------------------------------------------------------------------
class SetTimeModal(discord.ui.Modal, title="Set Time (UTC)"):
    def __init__(self, key, current_value, bot, guild_id, parent_view=None, weekly=False):
        super().__init__()
        self.key = key
        self.bot = bot
        self.guild_id = guild_id
        self.parent_view = parent_view
        self.weekly = weekly
        label = "Time (e.g. Monday 18:00)" if weekly else "Time (HH:MM)"
        placeholder = "Monday 18:00" if weekly else "12:00"
        self.add_item(discord.ui.TextInput(label=label, placeholder=placeholder, default=current_value))

    async def on_submit(self, interaction: discord.Interaction):
        value = self.children[0].value.strip()
        if self.weekly:
            parts = value.split()
            if len(parts) != 2:
                await interaction.response.send_message("❌ Format: Day HH:MM, e.g. Monday 18:00", ephemeral=True)
                return
            try:
                hour, minute = map(int, parts[1].split(':'))
            except:
                await interaction.response.send_message("❌ Invalid time.", ephemeral=True)
                return
        else:
            try:
                hour, minute = map(int, value.split(':'))
            except:
                await interaction.response.send_message("❌ Use HH:MM format.", ephemeral=True)
                return

        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO configs (guild_id, key, value) VALUES ($1,$2,$3) "
                "ON CONFLICT (guild_id,key) DO UPDATE SET value=$3",
                self.guild_id, self.key, value
            )
        msg = f"✅ Time set to **{value}** UTC"
        view = self.parent_view if self.parent_view else None
        await interaction.response.edit_message(content=msg, view=view)
        if view:
            view.message = await interaction.original_response()

class SetColourModal(discord.ui.Modal, title="Embed Colour"):
    def __init__(self, bot, guild_id, current_value, parent_view=None):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.parent_view = parent_view
        self.add_item(discord.ui.TextInput(label="Hex colour (e.g. dc2626)", placeholder="dc2626", default=current_value))

    async def on_submit(self, interaction: discord.Interaction):
        colour = self.children[0].value.strip().lstrip('#')
        if not re.match(r'^[0-9a-fA-F]{6}$', colour):
            await interaction.response.send_message("❌ Invalid hex colour. Use 6 characters.", ephemeral=True)
            return
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO configs (guild_id, key, value) VALUES ($1,'embed_color',$2) "
                "ON CONFLICT (guild_id,key) DO UPDATE SET value=$2",
                self.guild_id, colour
            )
        msg = f"✅ Embed colour set to #{colour}"
        view = self.parent_view if self.parent_view else None
        await interaction.response.edit_message(content=msg, view=view)
        if view:
            view.message = await interaction.original_response()

class AddTextModal(discord.ui.Modal, title="Add Custom Text"):
    def __init__(self, setting_key, item_name, bot, guild_id, parent_view=None):
        super().__init__()
        self.setting_key = setting_key
        self.item_name = item_name
        self.bot = bot
        self.guild_id = guild_id
        self.parent_view = parent_view
        self.add_item(discord.ui.TextInput(label=f"New {item_name}", style=discord.TextStyle.long))

    async def on_submit(self, interaction: discord.Interaction):
        text = self.children[0].value.strip()
        if not text:
            await interaction.response.send_message("❌ Cannot be empty.", ephemeral=True)
            return
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM configs WHERE guild_id=$1 AND key=$2",
                self.guild_id, self.setting_key
            )
            items = json.loads(row['value']) if row else []
            items.append(text)
            await conn.execute(
                "INSERT INTO configs (guild_id, key, value) VALUES ($1,$2,$3) "
                "ON CONFLICT (guild_id,key) DO UPDATE SET value=$3",
                self.guild_id, self.setting_key, json.dumps(items)
            )
        await interaction.response.edit_message(
            content=f"✅ Added {self.item_name}: **{text}**",
            view=self.parent_view
        )
        self.parent_view.message = await interaction.original_response()

class RemoveItemView(BaseConfigView):
    def __init__(self, bot, guild_id, setting_key, items, parent_menu=None):
        super().__init__(bot, guild_id, timeout=120)
        self.setting_key = setting_key
        self.parent_menu = parent_menu
        self.items = items
        options = [discord.SelectOption(label=item[:80], value=str(i)) for i, item in enumerate(items)]
        self.select_menu.options = options

    @discord.ui.select(placeholder="Select an item to remove...", min_values=1, max_values=1)
    async def select_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        idx = int(select.values[0])
        removed = self.items.pop(idx)
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO configs (guild_id, key, value) VALUES ($1,$2,$3) "
                "ON CONFLICT (guild_id,key) DO UPDATE SET value=$3",
                self.guild_id, self.setting_key, json.dumps(self.items)
            )
        await interaction.response.edit_message(
            content=f"🗑️ Removed: **{removed}**",
            view=self.parent_menu
        )
        self.parent_menu.message = await interaction.original_response()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=self.parent_menu)
        self.parent_menu.message = await interaction.original_response()

# ------------------------------------------------------------------
# The actual AutoPost cog (the one that runs scheduled posts)
# ------------------------------------------------------------------
class AutoPost(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_tip.start()
        self.weekly_scene.start()

    def cog_unload(self):
        self.daily_tip.cancel()
        self.weekly_scene.cancel()

    # --- Helper: get a setting ---
    async def get_setting(self, guild_id, key, default=None):
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM configs WHERE guild_id=$1 AND key=$2",
                guild_id, key
            )
            return row['value'] if row else default

    # --- Helper: get a random image from the images folder ---
    def get_random_image(self):
        image_dir = os.path.join(os.path.dirname(__file__), '..', 'images')
        if not os.path.isdir(image_dir):
            return None
        valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
        try:
            files = [f for f in os.listdir(image_dir) if f.lower().endswith(valid_extensions)]
            if not files:
                return None
            chosen = random.choice(files)
            return os.path.join(image_dir, chosen)
        except Exception as e:
            logger.warning(f"Could not read images folder: {e}")
            return None

    # --- Helper: get a channel by setting key ---
    async def get_channel_by_setting(self, guild, key):
        channel_id_str = await self.get_setting(guild.id, key)
        if not channel_id_str:
            return None
        try:
            channel_id = int(channel_id_str)
        except ValueError:
            return None
        return guild.get_channel(channel_id)

    # --- Helper: send an embed (with optional image and role mention) ---
    async def _send_embed(self, channel, title, description, color=0xDC2626,
                          footer="BDSM Collective • Stay safe, stay kinky",
                          mention_role=None):
        image_path = self.get_random_image()
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text=footer)
        file = None
        if image_path:
            file = discord.File(image_path, filename=os.path.basename(image_path))
            embed.set_image(url=f"attachment://{os.path.basename(image_path)}")
        content = None
        if mention_role and channel.guild:
            role = channel.guild.get_role(mention_role)
            if role:
                content = role.mention
        await channel.send(content=content, embed=embed, file=file)

    # --- Daily tip loop ---
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
                custom_tips_json = await self.get_setting(guild.id, "custom_tips")
                custom_tips = json.loads(custom_tips_json) if custom_tips_json else []
                all_tips = tips + custom_tips if custom_tips else tips
                color = await self.get_setting(guild.id, "embed_color", "dc2626")
                color_int = int(color, 16) if color else 0xDC2626
                mention_role_id = await self.get_setting(guild.id, "mention_role_id")
                mention_role_id = int(mention_role_id) if mention_role_id and mention_role_id.isdigit() else None
                await self._send_embed(channel, "🌟 Daily Kink Tip", random.choice(all_tips),
                                       color=color_int, mention_role=mention_role_id)
                logger.info(f"Daily tip sent to {guild.name} / #{channel.name}")
            except discord.Forbidden:
                logger.warning(f"No permission in {guild.name}")
            except discord.HTTPException as e:
                logger.error(f"HTTP error in {guild.name}: {e}")
            except Exception:
                logger.exception(f"Unexpected error in daily tip for {guild.name}")

    # --- Weekly scene loop ---
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
                custom_scenes_json = await self.get_setting(guild.id, "custom_scenes")
                custom_scenes = json.loads(custom_scenes_json) if custom_scenes_json else []
                all_scenes = default_scenes + custom_scenes if custom_scenes else default_scenes
                color = await self.get_setting(guild.id, "embed_color", "dc2626")
                color_int = int(color, 16) if color else 0xDC2626
                mention_role_id = await self.get_setting(guild.id, "mention_role_id")
                mention_role_id = int(mention_role_id) if mention_role_id and mention_role_id.isdigit() else None
                await self._send_embed(channel, "📋 Weekly Scene Prompt", random.choice(all_scenes),
                                       color=color_int, footer="BDSM Collective • Play responsibly",
                                       mention_role=mention_role_id)
                logger.info(f"Weekly scene sent to {guild.name} / #{channel.name}")
            except discord.Forbidden:
                logger.warning(f"No permission in {guild.name}")
            except discord.HTTPException as e:
                logger.error(f"HTTP error in {guild.name}: {e}")
            except Exception:
                logger.exception(f"Unexpected error in weekly scene for {guild.name}")

    @daily_tip.before_loop
    @weekly_scene.before_loop
    async def before_loops(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(10)

async def setup(bot):
    await bot.add_cog(AutoPost(bot))
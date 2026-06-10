import os
import re
import json
import random
import asyncio
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("kinkbot")

# ------------------- Base View with Database Helpers -------------------
class BaseConfigView(discord.ui.View):
    """Base class for all config views with database helper methods"""
    def __init__(self, bot, guild_id, timeout=600):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.guild_id = guild_id
        self.message = None

    async def get_setting(self, key, default=None):
        try:
            async with self.bot.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT value FROM configs WHERE guild_id=$1 AND key=$2",
                    self.guild_id, key
                )
                return row['value'] if row else default
        except Exception as e:
            logger.error(f"DB error in get_setting for {key}: {e}")
            return default

    async def set_setting(self, key, value):
        try:
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO configs (guild_id, key, value) VALUES ($1,$2,$3) "
                    "ON CONFLICT (guild_id,key) DO UPDATE SET value=$3",
                    self.guild_id, key, str(value)
                )
        except Exception as e:
            logger.error(f"DB error in set_setting for {key}: {e}")

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⏰ Admin panel timed out. Use `/admin` again.", view=None)
            except:
                pass

# ------------------- Cog -------------------
class AdminPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="admin", description="Open the admin control panel")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def admin(self, interaction: discord.Interaction):
        view = MainMenu(bot=self.bot, guild_id=interaction.guild_id)
        embed = discord.Embed(
            title="⚙️ BDSM Collective Admin Panel",
            description="Select a category to configure.",
            color=0xdc2626
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(AdminPanel(bot))

# ------------------- Main Menu -------------------
class MainMenu(BaseConfigView):
    def __init__(self, bot, guild_id):
        super().__init__(bot, guild_id, timeout=600)

    @discord.ui.button(label="Moderation", style=discord.ButtonStyle.red, emoji="🛡️")
    async def mod_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ModerationMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Moderation Settings**", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Auto-Post", style=discord.ButtonStyle.blurple, emoji="📅")
    async def auto_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AutoPostMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Auto-Post Settings**", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Server Config", style=discord.ButtonStyle.green, emoji="⚙️")
    async def config_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ServerConfigMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Server Configuration**", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="View Warnings", style=discord.ButtonStyle.gray, emoji="📋")
    async def warnings_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, reason, timestamp FROM warnings WHERE guild_id = $1 ORDER BY timestamp DESC LIMIT 10",
                interaction.guild_id
            )
            if not rows:
                await interaction.response.send_message("No warnings found.", ephemeral=True)
                return
            msg = "**Recent Warnings**\n" + "\n".join(
                f"<@{r['user_id']}> – {r['reason']} ({r['timestamp']})" for r in rows
            )
            await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="Create Embed Post", style=discord.ButtonStyle.grey, emoji="📝")
    async def embed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = EmbedBuilderView(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Embed Builder**", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, row=2)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Panel closed.", view=None)

# ------------------- Moderation Menu -------------------
class ModerationMenu(BaseConfigView):
    def __init__(self, bot, guild_id):
        super().__init__(bot, guild_id, timeout=600)

    @discord.ui.button(label="Spam Threshold", style=discord.ButtonStyle.secondary, emoji="📊")
    async def spam_threshold(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = await self.get_setting("spam_threshold", "5")
        modal = SetValueModal("spam_threshold", current, self.bot, self.guild_id, parent_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Add Profanity Word", style=discord.ButtonStyle.secondary, emoji="🔤")
    async def add_word(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddWordModal(self.bot, self.guild_id, parent_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Link Filter", style=discord.ButtonStyle.secondary, emoji="🔗")
    async def link_filter(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = await self.get_setting("link_filter", "true")
        new = "false" if current == "true" else "true"
        await self.set_setting("link_filter", new)
        button.style = discord.ButtonStyle.success if new == "true" else discord.ButtonStyle.secondary
        await interaction.response.edit_message(
            content=f"Link filter **{'enabled' if new=='true' else 'disabled'}**.", view=self
        )
        self.message = await interaction.original_response()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MainMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Admin Panel**", view=view)
        view.message = await interaction.original_response()

# ------------------- Auto-Post Menu (Full Settings) -------------------
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

        embed = discord.Embed(title=title, description=prompt, color=color_int)
        embed.set_footer(text="BDSM Collective • Stay safe, stay kinky")

        content = None
        if mention_role_id:
            role = channel.guild.get_role(mention_role_id)
            if role:
                content = role.mention

        await channel.send(content=content, embed=embed)
        await interaction.followup.send(f"✅ Test {post_type} post sent to {channel.mention}", ephemeral=True)

    async def _get_json_setting(self, key, default=None):
        val = await self.get_setting(key)
        if val is None:
            return default
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default

# ------------------- Server Config Menu -------------------
class ServerConfigMenu(BaseConfigView):
    def __init__(self, bot, guild_id):
        super().__init__(bot, guild_id, timeout=600)

    @discord.ui.button(label="Set Moderator Role", style=discord.ButtonStyle.success, emoji="🛡️")
    async def mod_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RoleSelectView(self.bot, self.guild_id, "mod_role_id", parent_menu=self)
        await interaction.response.edit_message(content="Select the moderator role:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Set Admin Role", style=discord.ButtonStyle.success, emoji="👑")
    async def admin_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RoleSelectView(self.bot, self.guild_id, "admin_role_id", parent_menu=self)
        await interaction.response.edit_message(content="Select the admin role:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Trusted Role", style=discord.ButtonStyle.success, emoji="⭐")
    async def trusted_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RoleSelectView(self.bot, self.guild_id, "trusted_role_id", parent_menu=self)
        await interaction.response.edit_message(content="Select the trusted role (bypasses link filter):", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Logging Channel", style=discord.ButtonStyle.success, emoji="#️⃣")
    async def log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChannelSelectView(self.bot, self.guild_id, "log_channel", parent_menu=self)
        await interaction.response.edit_message(content="Select a channel for moderation logs:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MainMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Admin Panel**", view=view)
        view.message = await interaction.original_response()

# ------------------- Channel Select (with placeholder) -------------------
class ChannelSelectView(BaseConfigView):
    def __init__(self, bot, guild_id, setting_key, parent_menu=None):
        super().__init__(bot, guild_id, timeout=120)
        self.setting_key = setting_key
        self.parent_menu = parent_menu
        options = self.get_channel_options()
        if not options:
            options = [discord.SelectOption(label="❌ No text channels found", value="0", default=True)]
        self.select_menu.options = options

    def get_channel_options(self):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return []
        options = []
        for channel in guild.text_channels:
            perms = channel.permissions_for(guild.me)
            if perms.read_messages and perms.send_messages:
                options.append(discord.SelectOption(label=channel.name, value=str(channel.id)))
        return options[:25]

    @discord.ui.select(placeholder="Choose a channel...", min_values=1, max_values=1)
    async def select_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values[0] == "0":
            await interaction.response.send_message("❌ No text channels available. Make sure I have `View Channel` and `Send Messages` permissions.", ephemeral=True)
            return
        channel_id = select.values[0]
        await self.set_setting(self.setting_key, channel_id)
        msg = f"✅ Channel set to <#{channel_id}>"
        view = self.parent_menu if self.parent_menu else None
        await interaction.response.edit_message(content=msg, view=view)
        if view:
            view.message = await interaction.original_response()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.parent_menu:
            await interaction.response.edit_message(view=self.parent_menu)
            self.parent_menu.message = await interaction.original_response()
        else:
            await interaction.response.edit_message(content="Cancelled.", view=None)

# ------------------- Role Select (with placeholder) -------------------
class RoleSelectView(BaseConfigView):
    def __init__(self, bot, guild_id, setting_key, parent_menu=None):
        super().__init__(bot, guild_id, timeout=120)
        self.setting_key = setting_key
        self.parent_menu = parent_menu
        options = self.get_role_options()
        if not options:
            options = [discord.SelectOption(label="❌ No roles available", value="0", default=True)]
        self.select_menu.options = options

    def get_role_options(self):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return []
        options = []
        for role in guild.roles:
            if role.name != "@everyone" and not role.managed:
                options.append(discord.SelectOption(label=role.name, value=str(role.id)))
        return options[:25]

    @discord.ui.select(placeholder="Select a role...", min_values=1, max_values=1)
    async def select_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values[0] == "0":
            await interaction.response.send_message("❌ No roles available. Make sure I have `View Channel` permission.", ephemeral=True)
            return
        role_id = select.values[0]
        await self.set_setting(self.setting_key, role_id)
        msg = f"✅ Role set to <@&{role_id}>"
        view = self.parent_menu if self.parent_menu else None
        await interaction.response.edit_message(content=msg, view=view)
        if view:
            view.message = await interaction.original_response()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.parent_menu:
            await interaction.response.edit_message(view=self.parent_menu)
            self.parent_menu.message = await interaction.original_response()
        else:
            await interaction.response.edit_message(content="Cancelled.", view=None)

# ──────────────── Old Modals (still used) ────────────────
class SetValueModal(discord.ui.Modal, title="Set Value"):
    def __init__(self, key, current_value, bot, guild_id, parent_view=None):
        super().__init__()
        self.key = key
        self.bot = bot
        self.guild_id = guild_id
        self.parent_view = parent_view
        self.add_item(discord.ui.TextInput(label="Value", default=current_value))

    async def on_submit(self, interaction: discord.Interaction):
        value = self.children[0].value
        if self.key == "spam_threshold":
            try:
                int(value)
            except ValueError:
                await interaction.response.send_message("❌ Spam threshold must be a number.", ephemeral=True)
                return
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO configs (guild_id, key, value) VALUES ($1,$2,$3) "
                "ON CONFLICT (guild_id,key) DO UPDATE SET value=$3",
                self.guild_id, self.key, value
            )
        msg = f"✅ Updated {self.key} to {value}"
        view = self.parent_view if self.parent_view else None
        await interaction.response.edit_message(content=msg, view=view)
        if view:
            view.message = await interaction.original_response()

class AddWordModal(discord.ui.Modal, title="Add Profanity Word"):
    def __init__(self, bot, guild_id, parent_view=None):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.parent_view = parent_view
        self.add_item(discord.ui.TextInput(label="Word to add"))

    async def on_submit(self, interaction: discord.Interaction):
        word = self.children[0].value.lower().strip()
        if not word:
            await interaction.response.send_message("❌ Word cannot be empty.", ephemeral=True)
            return
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM configs WHERE guild_id=$1 AND key='profanity_list'",
                self.guild_id
            )
            current = row['value'] if row else ""
            words = [w.strip() for w in current.split(',') if w.strip()]
            if word in words:
                await interaction.response.send_message(f"❌ '{word}' is already in the list.", ephemeral=True)
                return
            words.append(word)
            new_list = ','.join(words)
            await conn.execute(
                "INSERT INTO configs (guild_id, key, value) VALUES ($1,'profanity_list',$2) "
                "ON CONFLICT (guild_id,key) DO UPDATE SET value=$2",
                self.guild_id, new_list
            )
        msg = f"✅ Added profanity word: **{word}**"
        view = self.parent_view if self.parent_view else None
        await interaction.response.edit_message(content=msg, view=view)
        if view:
            view.message = await interaction.original_response()

# ──────────────── Embed Builder (full MVP) ────────────────
class EmbedBuilderView(BaseConfigView):
    def __init__(self, bot, guild_id):
        super().__init__(bot, guild_id, timeout=600)
        self.embed_data = {
            "title": None,
            "description": None,
            "color": 0xDC2626,
            "author_name": None,
            "author_icon_url": None,
            "footer_text": None,
            "footer_icon_url": None,
            "image_url": None,
            "thumbnail_url": None,
            "fields": []
        }
        self._file_path = None   # Path to local image file (mutually exclusive with image_url)
        self.preview_sent = False

    def build_embed(self) -> discord.Embed:
        """Construct an embed from current data."""
        embed = discord.Embed(
            title=self.embed_data["title"],
            description=self.embed_data["description"],
            color=self.embed_data["color"]
        )
        if self.embed_data["author_name"]:
            embed.set_author(
                name=self.embed_data["author_name"],
                icon_url=self.embed_data["author_icon_url"] or None
            )
        if self.embed_data["footer_text"]:
            embed.set_footer(
                text=self.embed_data["footer_text"],
                icon_url=self.embed_data["footer_icon_url"] or None
            )
        # Only set image URL if we're NOT using a local file
        if not self._file_path and self.embed_data["image_url"]:
            embed.set_image(url=self.embed_data["image_url"])
        if self.embed_data["thumbnail_url"]:
            embed.set_thumbnail(url=self.embed_data["thumbnail_url"])
        for field in self.embed_data["fields"]:
            embed.add_field(
                name=field["name"],
                value=field["value"],
                inline=field.get("inline", True)
            )
        return embed

    # ── Component buttons ──
    @discord.ui.button(label="Title", style=discord.ButtonStyle.primary, emoji="✏️", row=0)
    async def set_title(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SetTextModal("Title", "title", self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Description", style=discord.ButtonStyle.primary, emoji="📄", row=0)
    async def set_description(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SetTextModal("Description", "description", self, long=True)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Color", style=discord.ButtonStyle.primary, emoji="🎨", row=0)
    async def set_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SetColorModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Author", style=discord.ButtonStyle.primary, emoji="👤", row=1)
    async def set_author(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AuthorModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Footer", style=discord.ButtonStyle.primary, emoji="📌", row=1)
    async def set_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = FooterModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Image URL", style=discord.ButtonStyle.primary, emoji="🖼️", row=1)
    async def set_image_url(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = URLModal("Image URL", "image_url", self)
        await interaction.response.send_modal(modal)
        # Clear local file if set
        self._file_path = None

    @discord.ui.button(label="Image File", style=discord.ButtonStyle.primary, emoji="📂", row=2)
    async def set_image_file(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = FileSelectView(self.bot, self.guild_id, parent_builder=self)
        await interaction.response.edit_message(content="Select an image from the local folder:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Thumbnail URL", style=discord.ButtonStyle.primary, emoji="🔍", row=2)
    async def set_thumbnail(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = URLModal("Thumbnail URL", "thumbnail_url", self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Add Field", style=discord.ButtonStyle.success, emoji="➕", row=2)
    async def add_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.embed_data["fields"]) >= 25:
            await interaction.response.send_message("❌ Maximum 25 fields allowed.", ephemeral=True)
            return
        modal = AddFieldModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove Field", style=discord.ButtonStyle.danger, emoji="➖", row=3)
    async def remove_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.embed_data["fields"]:
            await interaction.response.send_message("No fields to remove.", ephemeral=True)
            return
        view = RemoveFieldView(self.bot, self.guild_id, self)
        await interaction.response.edit_message(content="Select a field to remove:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Preview", style=discord.ButtonStyle.secondary, emoji="👁️", row=3)
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.build_embed()
        if self._file_path:
            # Add a note that a local file will be attached on send
            embed.description = (embed.description or "") + "\n\n🖼️ *Local image file will be attached on send.*"
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Send", style=discord.ButtonStyle.success, emoji="📨", row=3)
    async def send_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.build_embed()
        view = SendChannelView(self.bot, self.guild_id, embed, self._file_path, parent_view=self)
        await interaction.response.edit_message(content="Select a channel to send the embed:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, row=3)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MainMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Admin Panel**", view=view)
        view.message = await interaction.original_response()

# ──────────────── File Select (local images) ────────────────
class FileSelectView(BaseConfigView):
    def __init__(self, bot, guild_id, parent_builder):
        super().__init__(bot, guild_id, timeout=120)
        self.parent_builder = parent_builder
        self.image_dir = os.path.join(os.path.dirname(__file__), '..', 'images')
        options = self._get_file_options()
        if not options:
            options = [discord.SelectOption(label="❌ No images found", value="0")]
        self.select_menu.options = options

    def _get_file_options(self):
        if not os.path.isdir(self.image_dir):
            return []
        valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
        options = []
        for f in sorted(os.listdir(self.image_dir)):
            if f.lower().endswith(valid_extensions):
                options.append(discord.SelectOption(label=f, value=f))
        return options[:25]

    @discord.ui.select(placeholder="Choose an image file...")
    async def select_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values[0] == "0":
            await interaction.response.send_message("❌ No image files found in the images folder.", ephemeral=True)
            return
        filename = select.values[0]
        file_path = os.path.join(self.image_dir, filename)
        self.parent_builder._file_path = file_path
        self.parent_builder.embed_data["image_url"] = None  # clear URL
        await interaction.response.edit_message(
            content=f"✅ Image file set to **{filename}**",
            view=self.parent_builder
        )
        self.parent_builder.message = await interaction.original_response()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="**Embed Builder**", view=self.parent_builder)
        self.parent_builder.message = await interaction.original_response()

# ──────────────── Send Channel Selector ────────────────
class SendChannelView(BaseConfigView):
    def __init__(self, bot, guild_id, embed, file_path=None, parent_view=None):
        super().__init__(bot, guild_id, timeout=120)
        self.embed = embed
        self.file_path = file_path   # Local image file path (optional)
        self.parent_view = parent_view
        options = self._get_channel_options()
        if not options:
            options = [discord.SelectOption(label="❌ No suitable channels", value="0")]
        self.select_menu.options = options

    def _get_channel_options(self):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return []
        options = []
        for channel in guild.text_channels:
            perms = channel.permissions_for(guild.me)
            if perms.send_messages and perms.embed_links:
                options.append(discord.SelectOption(label=channel.name, value=str(channel.id)))
        return options[:25]

    @discord.ui.select(placeholder="Choose a channel...")
    async def select_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values[0] == "0":
            await interaction.response.send_message("❌ No channels available.", ephemeral=True)
            return
        channel_id = int(select.values[0])
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        file = None
        if self.file_path:
            filename = os.path.basename(self.file_path)
            file = discord.File(self.file_path, filename=filename)
            self.embed.set_image(url=f"attachment://{filename}")

        try:
            await channel.send(embed=self.embed, file=file)
        except discord.Forbidden:
            await interaction.response.send_message(f"❌ Missing permissions in {channel.mention}.", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
            return

        if self.parent_view:
            await interaction.response.edit_message(
                content=f"✅ Embed sent to {channel.mention}",
                view=self.parent_view
            )
            self.parent_view.message = await interaction.original_response()
        else:
            await interaction.response.edit_message(content=f"✅ Embed sent to {channel.mention}", view=None)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.parent_view:
            await interaction.response.edit_message(content="**Embed Builder**", view=self.parent_view)
            self.parent_view.message = await interaction.original_response()
        else:
            await interaction.response.edit_message(content="Cancelled.", view=None)

# ──────────────── Remove Field Selector ────────────────
class RemoveFieldView(BaseConfigView):
    def __init__(self, bot, guild_id, parent_builder):
        super().__init__(bot, guild_id, timeout=120)
        self.parent_builder = parent_builder
        self.options = [
            discord.SelectOption(
                label=f"{f['name'][:80]}",
                value=str(i),
                description=f"Value: {f['value'][:50]}"
            )
            for i, f in enumerate(parent_builder.embed_data["fields"])
        ]
        if not self.options:
            self.options = [discord.SelectOption(label="No fields", value="-1")]
        self.select_menu.options = self.options

    @discord.ui.select(placeholder="Select a field to remove...")
    async def select_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        idx = int(select.values[0])
        if idx == -1:
            await interaction.response.edit_message(content="No fields to remove.", view=self.parent_builder)
            self.parent_builder.message = await interaction.original_response()
            return
        removed = self.parent_builder.embed_data["fields"].pop(idx)
        await interaction.response.edit_message(
            content=f"🗑️ Removed field: **{removed['name']}**",
            view=self.parent_builder
        )
        self.parent_builder.message = await interaction.original_response()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="**Embed Builder**", view=self.parent_builder)
        self.parent_builder.message = await interaction.original_response()

# ──────────────── Embed Builder Modals ────────────────
class SetTextModal(discord.ui.Modal):
    def __init__(self, field_name: str, data_key: str, builder_view, long=False):
        super().__init__(title=f"Set {field_name}")
        self.data_key = data_key
        self.builder = builder_view
        self.add_item(
            discord.ui.TextInput(
                label=field_name,
                style=discord.TextStyle.long if long else discord.TextStyle.short,
                placeholder=f"Enter {field_name.lower()}",
                default=builder_view.embed_data[data_key] or "",
                required=False,
                max_length=256 if data_key == "title" else 2048
            )
        )

    async def on_submit(self, interaction: discord.Interaction):
        value = self.children[0].value.strip() or None
        self.builder.embed_data[self.data_key] = value
        await interaction.response.edit_message(
            content=f"✅ {self.data_key.replace('_', ' ').title()} updated.",
            view=self.builder
        )
        self.builder.message = await interaction.original_response()

class SetColorModal(discord.ui.Modal, title="Set Color"):
    def __init__(self, builder_view):
        super().__init__()
        self.builder = builder_view
        current_hex = format(builder_view.embed_data["color"], '06x')
        self.add_item(
            discord.ui.TextInput(
                label="Hex color",
                placeholder="dc2626",
                default=current_hex,
                max_length=7
            )
        )

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.children[0].value.strip().lstrip('#')
        if not re.match(r'^[0-9a-fA-F]{6}$', raw):
            await interaction.response.send_message("❌ Invalid hex color.", ephemeral=True)
            return
        self.builder.embed_data["color"] = int(raw, 16)
        await interaction.response.edit_message(
            content=f"✅ Color set to #{raw}",
            view=self.builder
        )
        self.builder.message = await interaction.original_response()

class AuthorModal(discord.ui.Modal, title="Set Author"):
    def __init__(self, builder_view):
        super().__init__()
        self.builder = builder_view
        self.add_item(
            discord.ui.TextInput(
                label="Author name",
                placeholder="Your name",
                default=builder_view.embed_data["author_name"] or "",
                required=False,
                max_length=256
            )
        )
        self.add_item(
            discord.ui.TextInput(
                label="Author icon URL (optional)",
                placeholder="https://...",
                default=builder_view.embed_data["author_icon_url"] or "",
                required=False
            )
        )

    async def on_submit(self, interaction: discord.Interaction):
        name = self.children[0].value.strip() or None
        icon = self.children[1].value.strip() or None
        self.builder.embed_data["author_name"] = name
        self.builder.embed_data["author_icon_url"] = icon
        await interaction.response.edit_message(
            content="✅ Author updated.",
            view=self.builder
        )
        self.builder.message = await interaction.original_response()

class FooterModal(discord.ui.Modal, title="Set Footer"):
    def __init__(self, builder_view):
        super().__init__()
        self.builder = builder_view
        self.add_item(
            discord.ui.TextInput(
                label="Footer text",
                placeholder="Footer",
                default=builder_view.embed_data["footer_text"] or "",
                required=False,
                max_length=2048
            )
        )
        self.add_item(
            discord.ui.TextInput(
                label="Footer icon URL (optional)",
                placeholder="https://...",
                default=builder_view.embed_data["footer_icon_url"] or "",
                required=False
            )
        )

    async def on_submit(self, interaction: discord.Interaction):
        text = self.children[0].value.strip() or None
        icon = self.children[1].value.strip() or None
        self.builder.embed_data["footer_text"] = text
        self.builder.embed_data["footer_icon_url"] = icon
        await interaction.response.edit_message(
            content="✅ Footer updated.",
            view=self.builder
        )
        self.builder.message = await interaction.original_response()

class URLModal(discord.ui.Modal):
    def __init__(self, field_name: str, data_key: str, builder_view):
        super().__init__(title=f"Set {field_name}")
        self.data_key = data_key
        self.builder = builder_view
        self.add_item(
            discord.ui.TextInput(
                label=field_name,
                placeholder="https://example.com/image.png",
                default=builder_view.embed_data[data_key] or "",
                required=False
            )
        )

    async def on_submit(self, interaction: discord.Interaction):
        url = self.children[0].value.strip() or None
        if url and not url.startswith(("http://", "https://")):
            await interaction.response.send_message("❌ URL must start with http:// or https://", ephemeral=True)
            return
        self.builder.embed_data[self.data_key] = url
        await interaction.response.edit_message(
            content=f"✅ {self.data_key.replace('_', ' ').title()} updated.",
            view=self.builder
        )
        self.builder.message = await interaction.original_response()

class AddFieldModal(discord.ui.Modal, title="Add Field"):
    def __init__(self, builder_view):
        super().__init__()
        self.builder = builder_view
        self.add_item(
            discord.ui.TextInput(label="Field name", placeholder="Important", max_length=256)
        )
        self.add_item(
            discord.ui.TextInput(label="Field value", placeholder="Value", style=discord.TextStyle.long, max_length=1024)
        )
        self.add_item(
            discord.ui.TextInput(label="Inline (yes/no)", placeholder="yes", default="yes", required=False, max_length=3)
        )

    async def on_submit(self, interaction: discord.Interaction):
        name = self.children[0].value.strip()
        value = self.children[1].value.strip()
        inline_str = self.children[2].value.strip().lower()
        inline = inline_str != "no"
        if not name or not value:
            await interaction.response.send_message("❌ Name and value cannot be empty.", ephemeral=True)
            return
        self.builder.embed_data["fields"].append({
            "name": name,
            "value": value,
            "inline": inline
        })
        await interaction.response.edit_message(
            content=f"✅ Field added: **{name}**",
            view=self.builder
        )
        self.builder.message = await interaction.original_response()

# ──────────────── Custom Tips/Scenes Sub‑Menus ────────────────
class CustomTipsMenu(BaseConfigView):
    def __init__(self, bot, guild_id):
        super().__init__(bot, guild_id, timeout=300)

    @discord.ui.button(label="Add Tip", style=discord.ButtonStyle.success, emoji="➕")
    async def add_tip(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddTextModal("custom_tips", "tip", self.bot, self.guild_id, parent_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove Tip", style=discord.ButtonStyle.danger, emoji="➖")
    async def remove_tip(self, interaction: discord.Interaction, button: discord.ui.Button):
        tips = await self._get_items()
        if not tips:
            await interaction.response.send_message("No custom tips to remove.", ephemeral=True)
            return
        view = RemoveItemView(self.bot, self.guild_id, "custom_tips", tips, parent_menu=self)
        await interaction.response.edit_message(content="Select a tip to remove:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="List Tips", style=discord.ButtonStyle.secondary, emoji="📋")
    async def list_tips(self, interaction: discord.Interaction, button: discord.ui.Button):
        tips = await self._get_items()
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

    async def _get_items(self):
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
        scenes = await self._get_items()
        if not scenes:
            await interaction.response.send_message("No custom scenes to remove.", ephemeral=True)
            return
        view = RemoveItemView(self.bot, self.guild_id, "custom_scenes", scenes, parent_menu=self)
        await interaction.response.edit_message(content="Select a scene to remove:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="List Scenes", style=discord.ButtonStyle.secondary, emoji="📋")
    async def list_scenes(self, interaction: discord.Interaction, button: discord.ui.Button):
        scenes = await self._get_items()
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

    async def _get_items(self):
        val = await self.get_setting("custom_scenes")
        if not val:
            return []
        try:
            return json.loads(val)
        except:
            return []

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

# ──────────────── Time/Colour Modals for AutoPost ────────────────
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
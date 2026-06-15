import os
import re
import json
import random
import asyncio
import logging
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands

# Import shared views
from cogs.base_view import BaseConfigView, ChannelSelectView, RoleSelectView, CategorySelectView

logger = logging.getLogger("kinkbot")

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

    @app_commands.command(name="uploadimage", description="Upload an image to the bot's image folder")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        file="The image file to upload",
        filename="Optional: custom filename (without extension)"
    )
    async def upload_image(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        filename: str = None
    ):
        """Save an uploaded image to the bot's images/ folder."""
        await interaction.response.defer(ephemeral=True)

        valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
        if not file.filename.lower().endswith(valid_extensions):
            await interaction.followup.send(
                "❌ Unsupported file type. Allowed: PNG, JPG, JPEG, GIF, WEBP.",
                ephemeral=True
            )
            return

        image_dir = os.path.join(os.path.dirname(__file__), '..', 'images')
        os.makedirs(image_dir, exist_ok=True)

        if filename:
            safe_name = re.sub(r'[^\w\-]', '_', filename.strip())
            if not safe_name:
                safe_name = "uploaded"
        else:
            base = os.path.splitext(file.filename)[0]
            safe_name = re.sub(r'[^\w\-]', '_', base)

        ext = os.path.splitext(file.filename)[1].lower()
        final_name = f"{safe_name}{ext}"

        final_path = os.path.join(image_dir, final_name)
        counter = 1
        while os.path.exists(final_path):
            name_no_ext = safe_name
            final_name = f"{name_no_ext}_{counter}{ext}"
            final_path = os.path.join(image_dir, final_name)
            counter += 1

        try:
            await file.save(final_path)
            await interaction.followup.send(
                f"✅ Image saved as `{final_name}` and is now available in the admin panel.",
                ephemeral=True
            )
            logger.info(f"Image uploaded by {interaction.user}: {final_name}")
        except Exception as e:
            logger.error(f"Failed to save uploaded image: {e}")
            await interaction.followup.send(
                "❌ Failed to save the image. Check bot permissions and disk space.",
                ephemeral=True
            )

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
        # Start three‑step wizard – first modal
        modal = EmbedStepOne(self.bot, self.guild_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Manage Images", style=discord.ButtonStyle.grey, emoji="🖼️")
    async def images_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ImageManagerView(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Image Manager**", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, row=2)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Panel closed.", view=None)

# ------------------- Image Manager View -------------------
class ImageManagerView(BaseConfigView):
    def __init__(self, bot, guild_id):
        super().__init__(bot, guild_id, timeout=300)
        self.image_dir = os.path.join(os.path.dirname(__file__), '..', 'images')
        self._refresh_options()

    def _refresh_options(self):
        options = self._get_file_options()
        if not options:
            options = [discord.SelectOption(label="❌ No images", value="0")]
        self.children[0].options = options

    def _get_file_options(self):
        if not os.path.isdir(self.image_dir):
            return []
        valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
        options = []
        for f in sorted(os.listdir(self.image_dir)):
            if f.lower().endswith(valid_extensions):
                options.append(discord.SelectOption(label=f, value=f))
        return options[:25]

    @discord.ui.select(placeholder="Select an image to delete...")
    async def image_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        filename = select.values[0]
        if filename == "0":
            await interaction.response.send_message("No images available.", ephemeral=True)
            return
        self._selected = filename
        await interaction.response.send_message(f"Image **{filename}** selected. Click **Delete** to remove it.", ephemeral=True)

    @discord.ui.button(label="Delete Selected", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not hasattr(self, '_selected') or not self._selected:
            await interaction.response.send_message("No image selected. Use the dropdown first.", ephemeral=True)
            return
        filepath = os.path.join(self.image_dir, self._selected)
        try:
            os.remove(filepath)
            await interaction.response.send_message(f"✅ Deleted **{self._selected}**.", ephemeral=True)
            logger.info(f"Image deleted by {interaction.user}: {self._selected}")
            del self._selected
            self._refresh_options()
            await interaction.edit_original_response(view=self)
        except Exception as e:
            logger.error(f"Error deleting image {self._selected}: {e}")
            await interaction.response.send_message("❌ Could not delete the file.", ephemeral=True)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MainMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Admin Panel**", view=view)
        view.message = await interaction.original_response()

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

# ------------------- Auto-Post Menu -------------------
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

    @discord.ui.button(label="Test Daily Post", style=discord.ButtonStyle.gray, emoji="🚀", row=4)
    async def test_daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._test_post(interaction, "daily")

    @discord.ui.button(label="Test Weekly Post", style=discord.ButtonStyle.gray, emoji="🚀", row=4)
    async def test_weekly(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._test_post(interaction, "weekly")

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, row=4)
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

    @discord.ui.button(label="Welcome Channel", style=discord.ButtonStyle.success, emoji="#️⃣")
    async def welcome_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChannelSelectView(self.bot, self.guild_id, "welcome_channel_id", parent_menu=self)
        await interaction.response.edit_message(content="Select the welcome channel:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Verification Category", style=discord.ButtonStyle.success, emoji="📂")
    async def verification_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CategorySelectView(self.bot, self.guild_id, "verification_category_id", parent_menu=self)
        await interaction.response.edit_message(content="Select the category for verification channels:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Verified Role", style=discord.ButtonStyle.success, emoji="✅")
    async def verified_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RoleSelectView(self.bot, self.guild_id, "verified_role_id", parent_menu=self)
        await interaction.response.edit_message(content="Select the role given to verified members:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MainMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Admin Panel**", view=view)
        view.message = await interaction.original_response()

# ---------------------------------------------------------------------
# Old Modals (still used)
# ---------------------------------------------------------------------
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

# ================= THREE‑STEP EMBED BUILDER WITH BUTTON BRIDGE =================

class EmbedStepOne(discord.ui.Modal, title="Step 1/3: Basic Info"):
    def __init__(self, bot, guild_id):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.add_item(discord.ui.TextInput(label="Title", required=False, max_length=256))
        self.add_item(discord.ui.TextInput(label="Description", style=discord.TextStyle.long, required=False, max_length=4000))
        self.add_item(discord.ui.TextInput(label="Color (hex, e.g. dc2626)", required=False, max_length=7))

    async def on_submit(self, interaction: discord.Interaction):
        # Store temporary data
        if not hasattr(self.bot, 'temp_embed_data'):
            self.bot.temp_embed_data = {}
        self.bot.temp_embed_data[interaction.user.id] = {
            "title": self.children[0].value,
            "description": self.children[1].value,
            "color": self.children[2].value
        }
        # Show a button to continue
        view = ContinueToStepTwo(self.bot, self.guild_id, interaction.user.id)
        await interaction.response.edit_message(content="✅ Basic info saved. Click below to continue.", view=view)

class ContinueToStepTwo(discord.ui.View):
    def __init__(self, bot, guild_id, user_id):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.message = None

    @discord.ui.button(label="Continue to Step 2 (Author & Footer)", style=discord.ButtonStyle.primary)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This panel is not for you.", ephemeral=True)
        embed_data = self.bot.temp_embed_data.get(self.user_id, {})
        modal = EmbedStepTwo(self.bot, self.guild_id, embed_data)
        await interaction.response.send_modal(modal)
        # Clean up temporary data after moving to step 2
        del self.bot.temp_embed_data[self.user_id]

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⏰ Time expired. Use `/admin` again.", view=None)
            except:
                pass

class EmbedStepTwo(discord.ui.Modal, title="Step 2/3: Author & Footer"):
    def __init__(self, bot, guild_id, embed_data):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.embed_data = embed_data
        self.add_item(discord.ui.TextInput(label="Author name", required=False, max_length=256))
        self.add_item(discord.ui.TextInput(label="Author icon URL", required=False))
        self.add_item(discord.ui.TextInput(label="Footer text", required=False, max_length=2048))
        self.add_item(discord.ui.TextInput(label="Footer icon URL", required=False))

    async def on_submit(self, interaction: discord.Interaction):
        self.embed_data["author_name"] = self.children[0].value
        self.embed_data["author_icon"] = self.children[1].value
        self.embed_data["footer_text"] = self.children[2].value
        self.embed_data["footer_icon"] = self.children[3].value
        modal = EmbedStepThree(self.bot, self.guild_id, self.embed_data)
        await interaction.response.send_modal(modal)

class EmbedStepThree(discord.ui.Modal, title="Step 3/3: Images"):
    def __init__(self, bot, guild_id, embed_data):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.embed_data = embed_data
        self.add_item(discord.ui.TextInput(label="Image URL", required=False))
        self.add_item(discord.ui.TextInput(label="Thumbnail URL", required=False))

    async def on_submit(self, interaction: discord.Interaction):
        self.embed_data["image_url"] = self.children[0].value
        self.embed_data["thumbnail_url"] = self.children[1].value

        # Build the embed from collected data
        embed = discord.Embed()
        if self.embed_data.get("title"):
            embed.title = self.embed_data["title"]
        if self.embed_data.get("description"):
            embed.description = self.embed_data["description"]
        if self.embed_data.get("color"):
            try:
                color_hex = self.embed_data["color"].strip('#')
                embed.color = int(color_hex, 16)
            except:
                pass
        if self.embed_data.get("author_name"):
            embed.set_author(name=self.embed_data["author_name"], icon_url=self.embed_data.get("author_icon") or None)
        if self.embed_data.get("footer_text"):
            embed.set_footer(text=self.embed_data["footer_text"], icon_url=self.embed_data.get("footer_icon") or None)
        if self.embed_data.get("image_url"):
            embed.set_image(url=self.embed_data["image_url"])
        if self.embed_data.get("thumbnail_url"):
            embed.set_thumbnail(url=self.embed_data["thumbnail_url"])

        # Show fields & send view
        view = EmbedFieldsView(self.bot, self.guild_id, embed)
        await interaction.response.edit_message(content="**Embed Builder – Fields & Send**\nUse the buttons below to add fields, then click Send.", view=view)
        view.message = await interaction.original_response()

class EmbedFieldsView(BaseConfigView):
    def __init__(self, bot, guild_id, embed):
        super().__init__(bot, guild_id, timeout=600)
        self.embed = embed
        self.fields = []

    @discord.ui.button(label="Add Field", style=discord.ButtonStyle.success, emoji="➕")
    async def add_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.fields) >= 25:
            await interaction.response.send_message("❌ Maximum 25 fields allowed.", ephemeral=True)
            return
        modal = AddFieldModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove Field", style=discord.ButtonStyle.danger, emoji="➖")
    async def remove_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.fields:
            await interaction.response.send_message("No fields to remove.", ephemeral=True)
            return
        view = RemoveFieldView(self.bot, self.guild_id, self.fields, parent_view=self)
        await interaction.response.edit_message(content="Select a field to remove:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Preview", style=discord.ButtonStyle.secondary, emoji="👁️")
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        temp_embed = self.embed.copy()
        for f in self.fields:
            temp_embed.add_field(name=f['name'], value=f['value'], inline=f.get('inline', True))
        if not temp_embed.title and not temp_embed.description and not temp_embed.fields:
            await interaction.response.send_message("⚠️ Embed is empty. Add a title, description, or fields first.", ephemeral=True)
            return
        await interaction.response.send_message(embed=temp_embed, ephemeral=True)

    @discord.ui.button(label="Send", style=discord.ButtonStyle.success, emoji="📨")
    async def send_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        for f in self.fields:
            self.embed.add_field(name=f['name'], value=f['value'], inline=f.get('inline', True))
        view = SendChannelView(self.bot, self.guild_id, self.embed, parent_view=self)
        await interaction.response.edit_message(content="Select a channel to send the embed:", view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MainMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Admin Panel**", view=view)
        view.message = await interaction.original_response()

class AddFieldModal(discord.ui.Modal, title="Add Field"):
    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view
        self.add_item(discord.ui.TextInput(label="Field name", max_length=256))
        self.add_item(discord.ui.TextInput(label="Field value", style=discord.TextStyle.long, max_length=1024))
        self.add_item(discord.ui.TextInput(label="Inline (yes/no)", placeholder="yes", default="yes", max_length=3))

    async def on_submit(self, interaction: discord.Interaction):
        name = self.children[0].value.strip()
        value = self.children[1].value.strip()
        inline = self.children[2].value.strip().lower() != "no"
        if not name or not value:
            await interaction.response.send_message("❌ Name and value cannot be empty.", ephemeral=True)
            return
        self.parent_view.fields.append({"name": name, "value": value, "inline": inline})
        await interaction.response.edit_message(content=f"✅ Field added: **{name}**", view=self.parent_view)
        self.parent_view.message = await interaction.original_response()

class RemoveFieldView(BaseConfigView):
    def __init__(self, bot, guild_id, fields, parent_view):
        super().__init__(bot, guild_id, timeout=120)
        self.fields = fields
        self.parent_view = parent_view
        options = [discord.SelectOption(label=f"{f['name'][:80]}", value=str(i)) for i, f in enumerate(fields)]
        self.select_menu.options = options

    @discord.ui.select(placeholder="Select a field to remove...")
    async def select_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        idx = int(select.values[0])
        removed = self.fields.pop(idx)
        await interaction.response.edit_message(content=f"🗑️ Removed field: **{removed['name']}**", view=self.parent_view)
        self.parent_view.message = await interaction.original_response()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=self.parent_view)
        self.parent_view.message = await interaction.original_response()

# ------------------- Send Channel Selector -------------------
class SendChannelView(BaseConfigView):
    def __init__(self, bot, guild_id, embed, file_path=None, parent_view=None):
        super().__init__(bot, guild_id, timeout=120)
        self.embed = embed
        self.file_path = file_path
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

        try:
            await channel.send(embed=self.embed)
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

# ------------------- Custom Tips/Scenes Sub‑Menus -------------------
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

# ------------------- Time/Colour Modals for AutoPost -------------------
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
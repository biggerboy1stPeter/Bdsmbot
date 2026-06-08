import os
import discord
from discord import app_commands
from discord.ext import commands

# ------------------- Base View with Database Helpers -------------------
class BaseConfigView(discord.ui.View):
    """Base class for all config views with database helper methods"""
    def __init__(self, bot, guild_id, timeout=600):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.guild_id = guild_id

    async def get_setting(self, key, default=None):
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM configs WHERE guild_id=$1 AND key=$2",
                self.guild_id, key
            )
            return row['value'] if row else default

    async def set_setting(self, key, value):
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO configs (guild_id, key, value) VALUES ($1,$2,$3) "
                "ON CONFLICT (guild_id,key) DO UPDATE SET value=$3",
                self.guild_id, key, str(value)
            )

    async def on_timeout(self):
        """Disable all items when the view times out."""
        for child in self.children:
            child.disabled = True
        # To edit the original message you must store it when sending the view.
        # We don't have self.message, so this is a no‑op. You can implement
        # message capturing if needed.
        # try:
        #     await self.message.edit(view=self)
        # except:
        #     pass

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

    @discord.ui.button(label="Auto-Post", style=discord.ButtonStyle.blurple, emoji="📅")
    async def auto_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AutoPostMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Auto-Post Settings**", view=view)

    @discord.ui.button(label="Server Config", style=discord.ButtonStyle.green, emoji="⚙️")
    async def config_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ServerConfigMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Server Configuration**", view=view)

    @discord.ui.button(label="View Warnings", style=discord.ButtonStyle.gray, emoji="📋")
    async def warnings_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, reason, timestamp FROM warnings ORDER BY timestamp DESC LIMIT 10"
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
        modal = EmbedModal(self.bot, interaction.guild_id)
        await interaction.response.send_modal(modal)

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

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MainMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Admin Panel**", view=view)

# ------------------- Auto-Post Menu -------------------
class AutoPostMenu(BaseConfigView):
    def __init__(self, bot, guild_id):
        super().__init__(bot, guild_id, timeout=600)

    @discord.ui.button(label="Set Tips Channel", style=discord.ButtonStyle.success, emoji="#️⃣")
    async def tips_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChannelSelectView(self.bot, self.guild_id, "tips_channel", parent_menu=self)
        await interaction.response.edit_message(content="Select a channel for daily tips:", view=view)

    @discord.ui.button(label="Set Scenes Channel", style=discord.ButtonStyle.success, emoji="#️⃣")
    async def scenes_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChannelSelectView(self.bot, self.guild_id, "scenes_channel", parent_menu=self)
        await interaction.response.edit_message(content="Select a channel for weekly scene ideas:", view=view)

    @discord.ui.button(label="Toggle Daily Tip", style=discord.ButtonStyle.primary, emoji="✅")
    async def toggle_daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = await self.get_setting("daily_tip_enabled", "true")
        new = "false" if current == "true" else "true"
        await self.set_setting("daily_tip_enabled", new)
        button.label = "Daily Tip: ON" if new == "true" else "Daily Tip: OFF"
        button.style = discord.ButtonStyle.success if new == "true" else discord.ButtonStyle.danger
        await interaction.response.edit_message(
            content=f"Daily tip {'enabled ✅' if new=='true' else 'disabled ❌'}.", view=self
        )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MainMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Admin Panel**", view=view)

# ------------------- Server Config Menu -------------------
class ServerConfigMenu(BaseConfigView):
    def __init__(self, bot, guild_id):
        super().__init__(bot, guild_id, timeout=600)

    @discord.ui.button(label="Set Moderator Role", style=discord.ButtonStyle.success, emoji="🛡️")
    async def mod_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RoleSelectView(self.bot, self.guild_id, "mod_role_id", parent_menu=self)
        await interaction.response.edit_message(content="Select the moderator role:", view=view)

    @discord.ui.button(label="Set Admin Role", style=discord.ButtonStyle.success, emoji="👑")
    async def admin_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RoleSelectView(self.bot, self.guild_id, "admin_role_id", parent_menu=self)
        await interaction.response.edit_message(content="Select the admin role:", view=view)

    @discord.ui.button(label="Logging Channel", style=discord.ButtonStyle.success, emoji="#️⃣")
    async def log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChannelSelectView(self.bot, self.guild_id, "log_channel", parent_menu=self)
        await interaction.response.edit_message(content="Select a channel for moderation logs:", view=view)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MainMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Admin Panel**", view=view)

# ------------------- Channel Select (with Back button) -------------------
class ChannelSelectView(BaseConfigView):
    def __init__(self, bot, guild_id, setting_key, parent_menu=None):
        super().__init__(bot, guild_id, timeout=120)
        self.setting_key = setting_key
        self.parent_menu = parent_menu
        # Populate the select menu with channels
        self.select_menu.options = self.get_channel_options()

    def get_channel_options(self):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return []
        options = []
        for channel in guild.text_channels:
            options.append(discord.SelectOption(label=channel.name, value=str(channel.id)))
        return options[:25]

    @discord.ui.select(placeholder="Choose a channel...", min_values=1, max_values=1)
    async def select_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        channel_id = select.values[0]
        await self.set_setting(self.setting_key, channel_id)
        msg = f"✅ Channel set to <#{channel_id}>"
        view = self.parent_menu if self.parent_menu else None
        await interaction.response.edit_message(content=msg, view=view)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.parent_menu:
            await interaction.response.edit_message(view=self.parent_menu)
        else:
            await interaction.response.edit_message(content="Cancelled.", view=None)

# ------------------- Role Select (with Back button) -------------------
class RoleSelectView(BaseConfigView):
    def __init__(self, bot, guild_id, setting_key, parent_menu=None):
        super().__init__(bot, guild_id, timeout=120)
        self.setting_key = setting_key
        self.parent_menu = parent_menu
        self.select_menu.options = self.get_role_options()

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
        role_id = select.values[0]
        await self.set_setting(self.setting_key, role_id)
        msg = f"✅ Role set to <@&{role_id}>"
        view = self.parent_menu if self.parent_menu else None
        await interaction.response.edit_message(content=msg, view=view)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.parent_menu:
            await interaction.response.edit_message(view=self.parent_menu)
        else:
            await interaction.response.edit_message(content="Cancelled.", view=None)

# ------------------- Modals -------------------
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

class EmbedModal(discord.ui.Modal, title="Create Embed Post"):
    def __init__(self, bot, guild_id):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.add_item(discord.ui.TextInput(label="Channel ID"))
        self.add_item(discord.ui.TextInput(label="Title"))
        self.add_item(discord.ui.TextInput(label="Description", style=discord.TextStyle.long))
        self.add_item(discord.ui.TextInput(label="Color (hex)", placeholder="#dc2626", required=False))
        self.add_item(discord.ui.TextInput(label="Image filename (optional)", placeholder="announce.png", required=False))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel_id = int(self.children[0].value)
        except ValueError:
            await interaction.response.send_message("❌ Invalid channel ID.", ephemeral=True)
            return
        title = self.children[1].value
        desc = self.children[2].value
        color_hex = self.children[3].value or "#dc2626"
        image_file = self.children[4].value or None

        try:
            color = int(color_hex.lstrip('#'), 16)
        except ValueError:
            await interaction.response.send_message("❌ Invalid color hex.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return

        embed = discord.Embed(title=title, description=desc, color=color)
        embed.set_footer(text="BDSM Collective • Official Post")
        file = None
        if image_file:
            image_path = os.path.join(os.path.dirname(__file__), '..', 'images', image_file)
            if os.path.exists(image_path):
                file = discord.File(image_path, filename=image_file)
                embed.set_image(url=f"attachment://{image_file}")
            else:
                await interaction.response.send_message(f"❌ Image file not found: {image_file}", ephemeral=True)
                return

        await channel.send(embed=embed, file=file)
        await interaction.response.send_message(f"✅ Embed posted in {channel.mention}", ephemeral=True)

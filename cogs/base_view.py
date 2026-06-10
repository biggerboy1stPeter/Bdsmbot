import discord
import logging

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

# ------------------- Category Select (for Verification) -------------------
class CategorySelectView(BaseConfigView):
    def __init__(self, bot, guild_id, setting_key, parent_menu=None):
        super().__init__(bot, guild_id, timeout=120)
        self.setting_key = setting_key
        self.parent_menu = parent_menu
        options = self.get_category_options()
        if not options:
            options = [discord.SelectOption(label="❌ No categories found", value="0", default=True)]
        self.select_menu.options = options

    def get_category_options(self):
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return []
        options = []
        for channel in guild.categories:
            options.append(discord.SelectOption(label=channel.name, value=str(channel.id)))
        return options[:25]

    @discord.ui.select(placeholder="Choose a category...", min_values=1, max_values=1)
    async def select_menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values[0] == "0":
            await interaction.response.send_message("❌ No categories found.", ephemeral=True)
            return
        category_id = select.values[0]
        await self.set_setting(self.setting_key, category_id)
        msg = f"✅ Category set to <#{category_id}>"
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
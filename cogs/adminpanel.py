import discord
from discord import app_commands
from discord.ext import commands

class AdminPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="admin", description="Open the admin control panel")
    @app_commands.check(lambda i: i.user.guild_permissions.administrator)
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

# ------------------- Views & Modals -------------------
class MainMenu(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild_id

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
                "SELECT user_id, reason, timestamp FROM warnings WHERE user_id IN (SELECT user_id FROM profiles) ORDER BY timestamp DESC LIMIT 10"
            )
            if not rows:
                await interaction.response.edit_message(content="No warnings found.", view=None)
                return
            msg = "**Recent Warnings**\n" + "\n".join(
                f"<@{r['user_id']}> – {r['reason']} ({r['timestamp']})" for r in rows
            )
            await interaction.response.edit_message(content=msg, view=None)

    @discord.ui.button(label="Create Embed Post", style=discord.ButtonStyle.grey, emoji="📝")
    async def embed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EmbedModal(self.bot, interaction.guild_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, row=2)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Panel closed.", view=None)

# ------------------------------------------------------------
class ModerationMenu(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild_id

    async def get_setting(self, key, default=None):
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM configs WHERE guild_id=$1 AND key=$2", self.guild_id, key)
            return row['value'] if row else default

    async def set_setting(self, key, value):
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO configs (guild_id, key, value) VALUES ($1,$2,$3) ON CONFLICT (guild_id,key) DO UPDATE SET value=$3",
                self.guild_id, key, str(value)
            )

    @discord.ui.button(label="Spam Threshold", style=discord.ButtonStyle.secondary, emoji="📊")
    async def spam_threshold(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = await self.get_setting("spam_threshold", "5")
        await interaction.response.send_modal(SetValueModal("spam_threshold", current, self.bot, self.guild_id))

    @discord.ui.button(label="Add Profanity Word", style=discord.ButtonStyle.secondary, emoji="🔤")
    async def add_word(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddWordModal(self.bot, self.guild_id))

    @discord.ui.button(label="Link Filter", style=discord.ButtonStyle.secondary, emoji="🔗")
    async def link_filter(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = await self.get_setting("link_filter", "true")
        new = "false" if current == "true" else "true"
        await self.set_setting("link_filter", new)
        await interaction.response.edit_message(content=f"Link filter {'**enabled**' if new=='true' else '**disabled**'}.", view=self)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MainMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Admin Panel**", view=view)

# ------------------------------------------------------------
class AutoPostMenu(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild_id

    async def get_setting(self, key, default=None):
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM configs WHERE guild_id=$1 AND key=$2", self.guild_id, key)
            return row['value'] if row else default

    async def set_setting(self, key, value):
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO configs (guild_id, key, value) VALUES ($1,$2,$3) ON CONFLICT (guild_id,key) DO UPDATE SET value=$3",
                self.guild_id, key, str(value)
            )

    @discord.ui.button(label="Set Tips Channel", style=discord.ButtonStyle.success, emoji="#️⃣")
    async def tips_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChannelSelectView(self.bot, self.guild_id, setting_key="tips_channel")
        await interaction.response.edit_message(content="Select a channel for daily tips:", view=view)

    @discord.ui.button(label="Set Scenes Channel", style=discord.ButtonStyle.success, emoji="#️⃣")
    async def scenes_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChannelSelectView(self.bot, self.guild_id, setting_key="scenes_channel")
        await interaction.response.edit_message(content="Select a channel for weekly scene ideas:", view=view)

    @discord.ui.button(label="Toggle Daily Tip", style=discord.ButtonStyle.primary, emoji="✅")
    async def toggle_daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = await self.get_setting("daily_tip_enabled", "true")
        new = "false" if current == "true" else "true"
        await self.set_setting("daily_tip_enabled", new)
        await interaction.response.edit_message(content=f"Daily tip {'enabled ✅' if new=='true' else 'disabled ❌'}.", view=self)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MainMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Admin Panel**", view=view)

# ------------------------------------------------------------
class ServerConfigMenu(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild_id

    @discord.ui.button(label="Set Moderator Role", style=discord.ButtonStyle.success, emoji="🛡️")
    async def mod_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RoleSelectView(self.bot, self.guild_id, setting_key="mod_role_id")
        await interaction.response.edit_message(content="Select the moderator role:", view=view)

    @discord.ui.button(label="Set Admin Role", style=discord.ButtonStyle.success, emoji="👑")
    async def admin_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RoleSelectView(self.bot, self.guild_id, setting_key="admin_role_id")
        await interaction.response.edit_message(content="Select the admin role:", view=view)

    @discord.ui.button(label="Logging Channel", style=discord.ButtonStyle.success, emoji="#️⃣")
    async def log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ChannelSelectView(self.bot, self.guild_id, setting_key="log_channel")
        await interaction.response.edit_message(content="Select a channel for moderation logs:", view=view)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MainMenu(self.bot, self.guild_id)
        await interaction.response.edit_message(content="**Admin Panel**", view=view)

# ------------------------------------------------------------
class ChannelSelectView(discord.ui.View):
    def __init__(self, bot, guild_id, setting_key):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.setting_key = setting_key
        self.children[0].options = self.get_channel_options()

    def get_channel_options(self):
        guild = self.bot.get_guild(self.guild_id)
        options = []
        for channel in guild.text_channels:
            options.append(discord.SelectOption(label=channel.name, value=str(channel.id)))
        return options[:25]

    @discord.ui.select(placeholder="Choose a channel...", min_values=1, max_values=1)
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        channel_id = select.values[0]
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO configs (guild_id, key, value) VALUES ($1,$2,$3) ON CONFLICT (guild_id,key) DO UPDATE SET value=$3",
                self.guild_id, self.setting_key, channel_id
            )
        await interaction.response.edit_message(content=f"✅ Channel set to <#{channel_id}>", view=None)

class RoleSelectView(discord.ui.View):
    def __init__(self, bot, guild_id, setting_key):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.setting_key = setting_key
        self.children[0].options = self.get_role_options()

    def get_role_options(self):
        guild = self.bot.get_guild(self.guild_id)
        options = []
        for role in guild.roles:
            if role.name != "@everyone" and not role.managed:
                options.append(discord.SelectOption(label=role.name, value=str(role.id)))
        return options[:25]

    @discord.ui.select(placeholder="Select a role...", min_values=1, max_values=1)
    async def role_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        role_id = select.values[0]
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO configs (guild_id, key, value) VALUES ($1,$2,$3) ON CONFLICT (guild_id,key) DO UPDATE SET value=$3",
                self.guild_id, self.setting_key, role_id
            )
        await interaction.response.edit_message(content=f"✅ Role set to <@&{role_id}>", view=None)

# ------------------------------------------------------------
class SetValueModal(discord.ui.Modal, title="Set Value"):
    def __init__(self, key, current_value, bot, guild_id):
        super().__init__()
        self.key = key
        self.bot = bot
        self.guild_id = guild_id
        self.add_item(discord.ui.TextInput(label="Value", default=current_value))

    async def on_submit(self, interaction: discord.Interaction):
        value = self.children[0].value
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO configs (guild_id, key, value) VALUES ($1,$2,$3) ON CONFLICT (guild_id,key) DO UPDATE SET value=$3",
                self.guild_id, self.key, value
            )
        await interaction.response.edit_message(content=f"✅ Updated {self.key} to {value}", view=None)

class AddWordModal(discord.ui.Modal, title="Add Profanity Word"):
    def __init__(self, bot, guild_id):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.add_item(discord.ui.TextInput(label="Word to add"))

    async def on_submit(self, interaction: discord.Interaction):
        word = self.children[0].value.lower()
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM configs WHERE guild_id=$1 AND key='profanity_list'", self.guild_id)
            current = row['value'] if row else ""
            words = [w.strip() for w in current.split(',') if w.strip()]
            if word not in words:
                words.append(word)
            new_list = ','.join(words)
            await conn.execute(
                "INSERT INTO configs (guild_id, key, value) VALUES ($1,'profanity_list',$2) ON CONFLICT (guild_id,key) DO UPDATE SET value=$2",
                self.guild_id, new_list
            )
        await interaction.response.edit_message(content=f"✅ Added profanity word: **{word}**", view=None)

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
            await interaction.response.edit_message(content="❌ Invalid channel ID.", view=None)
            return
        title = self.children[1].value
        desc = self.children[2].value
        color_hex = self.children[3].value or "#dc2626"
        image_file = self.children[4].value or None

        try:
            color = int(color_hex.lstrip('#'), 16)
        except ValueError:
            await interaction.response.edit_message(content="❌ Invalid color hex.", view=None)
            return

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            await interaction.response.edit_message(content="❌ Channel not found.", view=None)
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
                await interaction.response.edit_message(content=f"❌ Image file not found: {image_file}", view=None)
                return

        await channel.send(embed=embed, file=file)
        await interaction.response.edit_message(content=f"✅ Embed posted in {channel.mention}", view=None)

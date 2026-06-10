import discord

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
            # logging is not imported here; we'll keep it minimal
            return default

    async def set_setting(self, key, value):
        try:
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO configs (guild_id, key, value) VALUES ($1,$2,$3) "
                    "ON CONFLICT (guild_id,key) DO UPDATE SET value=$3",
                    self.guild_id, key, str(value)
                )
        except Exception:
            pass

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⏰ Admin panel timed out. Use `/admin` again.", view=None)
            except:
                pass

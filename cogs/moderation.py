import discord
from discord.ext import commands
import re

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.spam_counter = {}

    async def get_setting(self, guild_id, key, default=None):
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM configs WHERE guild_id=$1 AND key=$2", guild_id, key)
            return row['value'] if row else default

    async def get_profanity_list(self, guild_id):
        words_str = await self.get_setting(guild_id, "profanity_list", "")
        return [w.strip() for w in words_str.split(',') if w.strip()] if words_str else []

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        guild_id = message.guild.id

        # Anti-spam (rapid messages)
        user_id = message.author.id
        now = discord.utils.utcnow()
        if user_id not in self.spam_counter:
            self.spam_counter[user_id] = []
        self.spam_counter[user_id] = [t for t in self.spam_counter[user_id] if (now - t).total_seconds() < 5]
        self.spam_counter[user_id].append(now)
        threshold = int(await self.get_setting(guild_id, "spam_threshold", "5"))
        if len(self.spam_counter[user_id]) > threshold:
            await message.author.timeout(discord.utils.utcnow() + discord.timedelta(minutes=5), reason="Spam")
            await message.channel.send(f"⏳ {message.author.mention} muted for 5 min (spam).")
            await self.log_warning(guild_id, user_id, self.bot.user.id, "Spam")
            return

        # Profanity filter
        profanity_list = await self.get_profanity_list(guild_id)
        if profanity_list:
            content = message.content.lower()
            for word in profanity_list:
                if re.search(rf'\b{re.escape(word)}\b', content):
                    await message.delete()
                    await message.channel.send(f"{message.author.mention} that word is not allowed here.")
                    return

        # Link filter
        link_filter_enabled = await self.get_setting(guild_id, "link_filter", "true")
        if link_filter_enabled == "true" and re.search(r'https?://', message.content):
            trusted_role = discord.utils.get(message.guild.roles, name="Trusted")
            if trusted_role not in message.author.roles:
                await message.delete()
                await message.channel.send("Links are not allowed without the Trusted role.")
                return

    async def log_warning(self, guild_id, user_id, mod_id, reason):
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO warnings (user_id, moderator_id, reason) VALUES ($1, $2, $3)",
                user_id, mod_id, reason
            )

    def is_admin():
        async def predicate(interaction: discord.Interaction):
            return interaction.user.guild_permissions.administrator
        return app_commands.check(predicate)

    @app_commands.command(name="kick")
    @is_admin()
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 Kicked {member.mention}")

    @app_commands.command(name="ban")
    @is_admin()
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 Banned {member.mention}")

    @app_commands.command(name="purge")
    @is_admin()
    async def purge(self, interaction: discord.Interaction, amount: int):
        if amount < 1 or amount > 100:
            await interaction.response.send_message("1-100 only.", ephemeral=True)
            return
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.response.send_message(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Moderation(bot))

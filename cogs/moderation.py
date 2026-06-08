import discord
from discord import app_commands
from discord.ext import commands
import re
import logging

logger = logging.getLogger("kinkbot")

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.spam_counter = {}  # Will be nested dict: {guild_id: {user_id: [timestamps]}}

    async def get_setting(self, guild_id, key, default=None):
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM configs WHERE guild_id=$1 AND key=$2", guild_id, key)
            return row['value'] if row else default

    async def get_profanity_list(self, guild_id):
        words_str = await self.get_setting(guild_id, "profanity_list", "")
        return [w.strip() for w in words_str.split(',') if w.strip()] if words_str else []

    async def log_warning(self, guild_id, user_id, mod_id, reason):
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO warnings (user_id, moderator_id, reason, guild_id) VALUES ($1, $2, $3, $4)",
                user_id, mod_id, reason, guild_id
            )

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bots and DMs
        if message.author.bot or not message.guild:
            return

        guild_id = message.guild.id
        user_id = message.author.id

        # --- Anti-spam ---
        # Initialize per-guild spam counter if needed
        if guild_id not in self.spam_counter:
            self.spam_counter[guild_id] = {}
        user_spam = self.spam_counter[guild_id].get(user_id, [])

        now = discord.utils.utcnow()
        # Keep only messages from last 5 seconds
        user_spam = [t for t in user_spam if (now - t).total_seconds() < 5]
        user_spam.append(now)
        self.spam_counter[guild_id][user_id] = user_spam

        spam_threshold = int(await self.get_setting(guild_id, "spam_threshold", "5"))
        if len(user_spam) > spam_threshold:
            try:
                await message.author.timeout(discord.utils.utcnow() + discord.timedelta(minutes=5), reason="Spam")
                await message.channel.send(f"⏳ {message.author.mention} muted for 5 min (spam).")
                await self.log_warning(guild_id, user_id, self.bot.user.id, "Spam")
            except discord.Forbidden:
                logger.warning(f"Could not timeout {message.author} in {message.guild.name}: missing permissions")
            except Exception as e:
                logger.error(f"Error timing out {message.author}: {e}")
            return  # Stop processing this message

        # --- Profanity filter ---
        profanity_list = await self.get_profanity_list(guild_id)
        if profanity_list:
            content = message.content.lower()
            for word in profanity_list:
                if re.search(rf'\b{re.escape(word)}\b', content):
                    try:
                        await message.delete()
                        await message.channel.send(f"{message.author.mention} that word is not allowed here.")
                        await self.log_warning(guild_id, user_id, self.bot.user.id, f"Profanity: {word}")
                    except discord.Forbidden:
                        logger.warning(f"Could not delete message from {message.author} in {message.guild.name}")
                    return

        # --- Link filter ---
        link_filter_enabled = await self.get_setting(guild_id, "link_filter", "true")
        if link_filter_enabled == "true" and re.search(r'https?://', message.content):
            # Get trusted role ID from config (default: "Trusted")
            trusted_role_id_str = await self.get_setting(guild_id, "trusted_role_id", None)
            trusted_role = None
            if trusted_role_id_str:
                try:
                    trusted_role = message.guild.get_role(int(trusted_role_id_str))
                except ValueError:
                    pass
            if not trusted_role:
                trusted_role = discord.utils.get(message.guild.roles, name="Trusted")
            if trusted_role not in message.author.roles:
                try:
                    await message.delete()
                    await message.channel.send("Links are not allowed without the Trusted role.")
                except discord.Forbidden:
                    logger.warning(f"Could not delete link message from {message.author}")
                return

    # ------------------- Slash commands -------------------
    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message("❌ You don't have permission to kick members.", ephemeral=True)
            return
        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(f"👢 Kicked {member.mention}")
            await self.log_warning(interaction.guild_id, member.id, interaction.user.id, f"Kick: {reason}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to kick that member.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message("❌ You don't have permission to ban members.", ephemeral=True)
            return
        try:
            await member.ban(reason=reason)
            await interaction.response.send_message(f"🔨 Banned {member.mention}")
            await self.log_warning(interaction.guild_id, member.id, interaction.user.id, f"Ban: {reason}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to ban that member.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="purge", description="Delete multiple messages in the current channel")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def purge(self, interaction: discord.Interaction, amount: int):
        if amount < 1 or amount > 100:
            await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You don't have permission to manage messages.", ephemeral=True)
            return
        try:
            deleted = await interaction.channel.purge(limit=amount)
            await interaction.response.send_message(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to delete messages.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
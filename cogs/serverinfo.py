import discord
from discord import app_commands
from discord.ext import commands

class ServerInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="serverinfo", description="Show detailed server information")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild

        # Basic info
        owner = guild.owner.mention if guild.owner else "Unknown"
        created = guild.created_at.strftime("%d %b %Y")
        member_count = guild.member_count
        # Count humans and bots (requires member intents)
        human_count = sum(1 for m in guild.members if not m.bot)
        bot_count = member_count - human_count if member_count else 0

        # Channel counts
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)

        # Boost info
        boost_level = guild.premium_tier
        boost_count = guild.premium_subscription_count or 0

        # Verification level
        verification = str(guild.verification_level).title()

        # Emojis & stickers
        emoji_count = len(guild.emojis)

        # Build embed
        embed = discord.Embed(title=guild.name, color=0xdc2626)
        embed.set_footer(text=f"Server ID: {guild.id}")

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="👑 Owner", value=owner, inline=True)
        embed.add_field(name="📅 Created", value=created, inline=True)
        embed.add_field(name="👥 Members", value=f"{member_count} total\n👤 {human_count} humans\n🤖 {bot_count} bots", inline=True)
        embed.add_field(name="💬 Channels", value=f"{text_channels} text\n{voice_channels} voice\n{categories} categories", inline=True)
        embed.add_field(name="✨ Boosts", value=f"Level {boost_level} ({boost_count} boosts)", inline=True)
        embed.add_field(name="🔒 Verification", value=verification, inline=True)
        embed.add_field(name="😀 Emojis", value=emoji_count, inline=True)

        # Optional: Banner (if available)
        if guild.banner:
            embed.set_image(url=guild.banner.url)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(ServerInfo(bot))
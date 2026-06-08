import discord
from discord import app_commands
from discord.ext import commands
import os

class AdminPost(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="postembed", description="Admin only: create a fancy embed post")
    @app_commands.describe(
        channel="Channel to post in",
        title="Embed title",
        description="Embed description",
        color="Hex color code (e.g. #dc2626)",
        image="Image filename from bot's images/ folder (optional)"
    )
    @app_commands.check(lambda i: i.user.guild_permissions.administrator)
    async def postembed(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        description: str,
        color: str = "#dc2626",
        image: str = None
    ):
        try:
            color_int = int(color.lstrip('#'), 16)
        except ValueError:
            await interaction.response.send_message("Invalid color hex.", ephemeral=True)
            return

        embed = discord.Embed(title=title, description=description, color=color_int)
        embed.set_footer(text="BDSM Collective • Official Post")

        file = None
        if image:
            image_path = os.path.join(os.path.dirname(__file__), '..', 'images', image)
            if os.path.exists(image_path):
                file = discord.File(image_path, filename=image)
                embed.set_image(url=f"attachment://{image}")
            else:
                await interaction.response.send_message(f"❌ Image file not found: {image}", ephemeral=True)
                return

        await channel.send(embed=embed, file=file)
        await interaction.response.send_message(f"✅ Embed posted in {channel.mention}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminPost(bot))

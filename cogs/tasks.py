import discord
from discord import app_commands
from discord.ext import commands
import random

class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="task", description="Get a random task or punishment")
    async def task(self, interaction: discord.Interaction):
        tasks = [
            "Write 10 lines about why you deserve to be punished.",
            "Edge for 10 minutes without permission to cum.",
            "Send a voice message begging in #general (with permission).",
            "Hold a plank for 2 minutes while reciting your safeword.",
            "Share one hard limit and why it exists.",
            "Wear your collar for the next hour.",
            "Write a gratitude list for your Dom/Domme.",
            "Do 20 push‑ups while holding eye contact with your reflection.",
            "Recite your rules from memory. Mistake = start over.",
            "Clean your toys and send a photo (if comfortable).",
        ]
        await interaction.response.send_message(f"🎲 **Task for {interaction.user.mention}:**\n{random.choice(tasks)}")

    @app_commands.command(name="aftercare", description="Get an aftercare reminder")
    async def aftercare(self, interaction: discord.Interaction):
        tips = [
            "Drink water and have a light snack.",
            "Cuddle or wrap yourself in a soft blanket.",
            "Talk about what you enjoyed and what you didn't.",
            "Write in your journal about the experience.",
            "Take a warm bath or shower together.",
        ]
        await interaction.response.send_message(f"🧸 **Aftercare Reminder:** {random.choice(tips)}")

async def setup(bot):
    await bot.add_cog(Tasks(bot))

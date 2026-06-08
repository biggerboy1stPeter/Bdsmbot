import discord
from discord import app_commands
from discord.ext import commands
import random
import logging

logger = logging.getLogger("kinkbot")

class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ------------------------------------------------------------
    # Helper: Get task list for a guild (custom + default fallback)
    # ------------------------------------------------------------
    async def get_guild_tasks(self, guild_id: int):
        """Return list of tasks for the guild (custom tasks if any, otherwise defaults)."""
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT task FROM custom_tasks WHERE guild_id = $1 ORDER BY created_at",
                guild_id
            )
        if rows:
            return [row['task'] for row in rows]
        else:
            # Default tasks (fallback)
            return [
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

    # ------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------
    @app_commands.command(name="task", description="Get a random task or punishment")
    @app_commands.describe(
        send_dm="Send the task to your DMs (private) instead of the channel",
        ephemeral="Only you see the response (only works in channel, not with DM)"
    )
    async def task(self, interaction: discord.Interaction, send_dm: bool = False, ephemeral: bool = False):
        # Get tasks for this guild
        tasks = await self.get_guild_tasks(interaction.guild_id)
        chosen = random.choice(tasks)

        # Handle DM delivery
        if send_dm:
            try:
                await interaction.user.send(f"🎲 **Task from {interaction.guild.name}:**\n{chosen}")
                await interaction.response.send_message("✅ Task sent to your DMs!", ephemeral=True)
                logger.info(f"Task DM sent to {interaction.user} in {interaction.guild.name}")
            except discord.Forbidden:
                await interaction.response.send_message("❌ I can't DM you. Please enable DMs from server members.", ephemeral=True)
            return

        # Channel delivery (with optional ephemeral)
        await interaction.response.send_message(
            f"🎲 **Task for {interaction.user.mention}:**\n{chosen}",
            ephemeral=ephemeral
        )
        logger.info(f"Task given to {interaction.user} in {interaction.guild.name} (ephemeral={ephemeral})")

    @app_commands.command(name="aftercare", description="Get an aftercare reminder")
    @app_commands.describe(ephemeral="Keep the reminder private")
    async def aftercare(self, interaction: discord.Interaction, ephemeral: bool = False):
        tips = [
            "🧴 Drink water and have a light snack.",
            "🛋️ Cuddle or wrap yourself in a soft blanket.",
            "💬 Talk about what you enjoyed and what you didn't.",
            "📓 Write in your journal about the experience.",
            "🛁 Take a warm bath or shower together.",
            "🎵 Listen to calming music or white noise.",
            "🍫 Eat something sweet – dark chocolate helps with oxytocin.",
            "🧘 Practice deep breathing for 2 minutes.",
        ]
        tip_text = random.choice(tips)
        await interaction.response.send_message(
            f"🧸 **Aftercare Reminder:**\n{tip_text}",
            ephemeral=ephemeral
        )
        logger.info(f"Aftercare reminder sent to {interaction.user}")

    # ------------------------------------------------------------
    # Admin commands to manage tasks
    # ------------------------------------------------------------
    @app_commands.command(name="addtask", description="[Admin] Add a custom task to the server")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def add_task(self, interaction: discord.Interaction, task: str):
        if len(task) > 500:
            await interaction.response.send_message("❌ Task is too long (max 500 chars).", ephemeral=True)
            return

        async with self.bot.db_pool.acquire() as conn:
            try:
                await conn.execute(
                    "INSERT INTO custom_tasks (guild_id, task) VALUES ($1, $2)",
                    interaction.guild_id, task
                )
                await interaction.response.send_message(f"✅ Task added:\n> {task}", ephemeral=True)
                logger.info(f"Admin {interaction.user} added task to {interaction.guild.name}: {task}")
            except Exception as e:
                await interaction.response.send_message("❌ Task already exists or database error.", ephemeral=True)
                logger.error(f"Failed to add task: {e}")

    @app_commands.command(name="removetask", description="[Admin] Remove a custom task by number")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def remove_task(self, interaction: discord.Interaction, number: int):
        async with self.bot.db_pool.acquire() as conn:
            # Get all tasks with row numbers
            rows = await conn.fetch(
                "SELECT task FROM custom_tasks WHERE guild_id = $1 ORDER BY created_at",
                interaction.guild_id
            )
            if not rows:
                await interaction.response.send_message("❌ No custom tasks to remove.", ephemeral=True)
                return
            if number < 1 or number > len(rows):
                await interaction.response.send_message(f"❌ Invalid number. Use 1 to {len(rows)}.", ephemeral=True)
                return

            task_to_remove = rows[number - 1]['task']
            await conn.execute(
                "DELETE FROM custom_tasks WHERE guild_id = $1 AND task = $2",
                interaction.guild_id, task_to_remove
            )
            await interaction.response.send_message(f"✅ Removed task #{number}:\n> {task_to_remove}", ephemeral=True)
            logger.info(f"Admin {interaction.user} removed task #{number} from {interaction.guild.name}")

    @app_commands.command(name="listtasks", description="[Admin] List all custom tasks for this server")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def list_tasks(self, interaction: discord.Interaction):
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT task FROM custom_tasks WHERE guild_id = $1 ORDER BY created_at",
                interaction.guild_id
            )
        if not rows:
            await interaction.response.send_message("No custom tasks. Use `/addtask` to add some.", ephemeral=True)
            return
        msg = "**Custom Tasks (numbered for removal):**\n"
        for idx, row in enumerate(rows, 1):
            msg += f"{idx}. {row['task']}\n"
            if len(msg) > 1900:
                msg += "... (truncated)"
                break
        await interaction.response.send_message(msg, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Tasks(bot))
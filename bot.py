import os
import asyncio
import asyncpg
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class KinkBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.db_pool = None

    async def setup_hook(self):
        # Connect to PostgreSQL
        try:
            self.db_pool = await asyncpg.create_pool(
                os.getenv("DATABASE_URL"),
                min_size=2,
                max_size=10
            )
            print("✅ Database connected")
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            exit(1)

        # List of cogs to load
        cogs = [
            "cogs.basics",
            "cogs.profiles",
            "cogs.collars",
            "cogs.moderation",
            "cogs.autopost",
            "cogs.adminpost",
            "cogs.adminpanel",
            "cogs.orders",
            "cogs.serverinfo",
            "cogs.tasks",
        ]

        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f"✅ Loaded {cog}")
            except Exception as e:
                print(f"❌ Failed to load {cog}: {e}")

        # Sync slash commands globally (can take up to an hour, but good for production)
        await self.tree.sync()
        print(f"✅ {self.user} is ready!")

    async def close(self):
        if self.db_pool:
            await self.db_pool.close()
        await super().close()

if __name__ == "__main__":
    bot = KinkBot()
    bot.run(os.getenv("DISCORD_TOKEN"))

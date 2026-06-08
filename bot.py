import os
import sys
import asyncio
import logging
from datetime import datetime

import asyncpg
import discord
from discord.ext import commands
from dotenv import load_dotenv
from aiohttp import web

# Load environment variables
load_dotenv()

# -------------------------------------------------------------------
# Console logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("kinkbot")

# -------------------------------------------------------------------
# Keep‑alive HTTP server
async def health_check(request):
    return web.Response(text="OK", status=200)

async def start_keep_alive(port: int = 8081):
    """Starts a minimal HTTP server for health checks."""
    app = web.Application()
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🔄 Keep‑alive server running on port {port}")

# -------------------------------------------------------------------
class KinkBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.db_pool = None
        self.start_time = datetime.now()

    async def setup_hook(self):
        # Connect to PostgreSQL
        logger.info("🔌 Connecting to database...")
        try:
            self.db_pool = await asyncpg.create_pool(
                os.getenv("DATABASE_URL"),
                min_size=2,
                max_size=10
            )
            logger.info("✅ Database connected")
        except Exception as e:
            logger.critical(f"❌ Database connection failed: {e}")
            sys.exit(1)

        # Start keep‑alive HTTP server
        keep_alive_port = int(os.getenv("KEEP_ALIVE_PORT", "8081"))
        asyncio.create_task(start_keep_alive(keep_alive_port))

        # Load all cogs (adminpost REMOVED)
        cogs = [
            "cogs.basics",
            "cogs.profiles",
            "cogs.collars",
            "cogs.moderation",
            "cogs.autopost",
            # "cogs.adminpost",   # <-- DELETED – standalone /postembed command removed
            "cogs.adminpanel",    # <-- this contains the modal inside the admin panel
            "cogs.orders",
            "cogs.serverinfo",
            "cogs.tasks",
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"✅ Loaded {cog}")
            except Exception as e:
                logger.error(f"❌ Failed to load {cog}: {e}")

        # Sync slash commands globally
        await self.tree.sync()
        logger.info(f"✅ Logged in as {self.user} (ID: {self.user.id})")

    async def close(self):
        logger.info("🛑 Shutting down...")
        if self.db_pool:
            await self.db_pool.close()
            logger.info("🔌 Database pool closed")
        await super().close()

# -------------------------------------------------------------------
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.critical("❌ DISCORD_TOKEN not set in .env")
        sys.exit(1)

    bot = KinkBot()
    try:
        bot.run(token, log_handler=None)  # log_handler=None to use our own logging
    except discord.LoginFailure:
        logger.critical("❌ Invalid bot token")
    except Exception as e:
        logger.critical(f"❌ Bot crashed: {e}")

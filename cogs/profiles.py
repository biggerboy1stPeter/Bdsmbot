import discord
from discord import app_commands
from discord.ext import commands

class Profiles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Set or view your BDSM profile")
    @app_commands.describe(role="Dom, Sub, or Switch", about="A short bio")
    async def profile(self, interaction: discord.Interaction, role: str = None, about: str = None):
        user_id = interaction.user.id
        async with self.bot.db_pool.acquire() as conn:
            if role or about:
                role = role.capitalize() if role else None
                if role and role not in ["Dom", "Sub", "Switch"]:
                    await interaction.response.send_message("Role must be Dom, Sub, or Switch.", ephemeral=True)
                    return
                await conn.execute("""
                    INSERT INTO profiles (user_id, role, about) VALUES ($1, $2, $3)
                    ON CONFLICT (user_id) DO UPDATE SET role = COALESCE($2, profiles.role), about = COALESCE($3, profiles.about)
                """, user_id, role, about)
                await interaction.response.send_message("✅ Profile updated!")
            else:
                row = await conn.fetchrow("SELECT role, about FROM profiles WHERE user_id = $1", user_id)
                if row:
                    msg = f"**{interaction.user.display_name}**\nRole: {row['role'] or 'N/A'}\nAbout: {row['about'] or 'N/A'}"
                else:
                    msg = "No profile set. Use `/profile role:Dom about:...`"
                await interaction.response.send_message(msg)

    @app_commands.command(name="kinklist", description="Manage your kink list")
    @app_commands.describe(kinks="Comma separated list of kinks")
    async def kinklist(self, interaction: discord.Interaction, kinks: str = None):
        user_id = interaction.user.id
        async with self.bot.db_pool.acquire() as conn:
            if kinks:
                kink_list = [k.strip().lower() for k in kinks.split(",") if k.strip()]
                await conn.execute("""
                    INSERT INTO kinklists (user_id, kinks) VALUES ($1, $2)
                    ON CONFLICT (user_id) DO UPDATE SET kinks = $2, updated_at = NOW()
                """, user_id, kink_list)
                await interaction.response.send_message(f"✅ Kinks updated:\n**{', '.join(kink_list)}**")
            else:
                row = await conn.fetchrow("SELECT kinks FROM kinklists WHERE user_id = $1", user_id)
                if row and row['kinks']:
                    await interaction.response.send_message(f"Kinks for {interaction.user.mention}:\n{', '.join(row['kinks'])}")
                else:
                    await interaction.response.send_message("No kinks set. Use `/kinklist your,kinks,here`")

async def setup(bot):
    await bot.add_cog(Profiles(bot))

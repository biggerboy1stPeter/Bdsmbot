import discord
from discord import app_commands
from discord.ext import commands
import logging

logger = logging.getLogger("kinkbot")

class Profiles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Set or view your BDSM profile")
    @app_commands.describe(role="Dom, Sub, or Switch", about="A short bio (max 500 chars)")
    async def profile(self, interaction: discord.Interaction, role: str = None, about: str = None):
        user_id = interaction.user.id

        # Validate and clean inputs
        if role is not None:
            role = role.strip().capitalize()
            if role not in ["Dom", "Sub", "Switch"]:
                await interaction.response.send_message("❌ Role must be Dom, Sub, or Switch.", ephemeral=True)
                return

        if about is not None and len(about) > 500:
            await interaction.response.send_message("❌ About text cannot exceed 500 characters.", ephemeral=True)
            return

        try:
            async with self.bot.db_pool.acquire() as conn:
                if role is not None or about is not None:
                    # Update profile
                    await conn.execute("""
                        INSERT INTO profiles (user_id, role, about) VALUES ($1, $2, $3)
                        ON CONFLICT (user_id) DO UPDATE SET
                            role = COALESCE($2, profiles.role),
                            about = COALESCE($3, profiles.about)
                    """, user_id, role, about)
                    await interaction.response.send_message("✅ Profile updated!", ephemeral=True)
                    logger.info(f"Profile updated for {interaction.user} (role={role}, about={about[:50] if about else None})")
                else:
                    # View profile
                    row = await conn.fetchrow("SELECT role, about FROM profiles WHERE user_id = $1", user_id)
                    if row:
                        embed = discord.Embed(
                            title=interaction.user.display_name,
                            description=row['about'] or "No bio set.",
                            color=0xdc2626
                        )
                        embed.add_field(name="Role", value=row['role'] or "Not specified", inline=False)
                        embed.set_thumbnail(url=interaction.user.display_avatar.url)
                        await interaction.response.send_message(embed=embed)
                    else:
                        await interaction.response.send_message(
                            "❌ No profile set. Use `/profile role:Dom about:Hello!` to create one.",
                            ephemeral=True
                        )
        except Exception as e:
            logger.error(f"Profile command error for {interaction.user}: {e}")
            await interaction.response.send_message("❌ Database error. Please try again later.", ephemeral=True)

    @app_commands.command(name="kinklist", description="Manage your kink list")
    @app_commands.describe(
        kinks="Comma-separated list of kinks (max 20 items, 50 chars each)",
        clear="Clear your entire kink list"
    )
    async def kinklist(self, interaction: discord.Interaction, kinks: str = None, clear: bool = False):
        user_id = interaction.user.id

        try:
            async with self.bot.db_pool.acquire() as conn:
                if clear:
                    await conn.execute("DELETE FROM kinklists WHERE user_id = $1", user_id)
                    await interaction.response.send_message("✅ Your kink list has been cleared.", ephemeral=True)
                    return

                if kinks is not None:
                    # Parse and validate kinks
                    kink_list = [k.strip().lower() for k in kinks.split(",") if k.strip()]
                    if len(kink_list) > 20:
                        await interaction.response.send_message("❌ Maximum 20 kinks allowed.", ephemeral=True)
                        return
                    for k in kink_list:
                        if len(k) > 50:
                            await interaction.response.send_message(f"❌ Kink '{k[:30]}...' exceeds 50 characters.", ephemeral=True)
                            return

                    # Store as PostgreSQL array (TEXT[])
                    await conn.execute("""
                        INSERT INTO kinklists (user_id, kinks) VALUES ($1, $2)
                        ON CONFLICT (user_id) DO UPDATE SET kinks = $2, updated_at = NOW()
                    """, user_id, kink_list)
                    await interaction.response.send_message(
                        f"✅ Kinks updated:\n**{', '.join(kink_list)}**",
                        ephemeral=True
                    )
                    logger.info(f"Kinklist updated for {interaction.user}: {len(kink_list)} items")
                else:
                    # View kink list
                    row = await conn.fetchrow("SELECT kinks FROM kinklists WHERE user_id = $1", user_id)
                    if row and row['kinks']:
                        # row['kinks'] is a list (TEXT[])
                        kink_items = row['kinks']
                        if kink_items:
                            embed = discord.Embed(
                                title=f"{interaction.user.display_name}'s Kink List",
                                description=", ".join(kink_items),
                                color=0xdc2626
                            )
                            embed.set_footer(text="Use /kinklist kinks:... to update | /kinklist clear:True to clear")
                            await interaction.response.send_message(embed=embed)
                        else:
                            await interaction.response.send_message("Your kink list is empty.", ephemeral=True)
                    else:
                        await interaction.response.send_message(
                            "❌ No kinks set. Use `/kinklist kinks:spanking,bondage,etc`",
                            ephemeral=True
                        )
        except Exception as e:
            logger.error(f"Kinklist command error for {interaction.user}: {e}")
            await interaction.response.send_message("❌ Database error. Please try again later.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Profiles(bot))
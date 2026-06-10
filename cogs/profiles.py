import json
import discord
from discord import app_commands
from discord.ext import commands
import logging

logger = logging.getLogger("kinkbot")


# ---------------------------------------------------------------------------
# Optional NSFW check: if you want to restrict profile viewing to NSFW channels
# or users who have an age gate, uncomment the decorator below and adjust logic.
# ---------------------------------------------------------------------------
# def nsfw_channel_only():
#     async def predicate(interaction: discord.Interaction):
#         if not interaction.channel.is_nsfw():
#             raise app_commands.AppCommandError("This command can only be used in NSFW channels.")
#         return True
#     return app_commands.check(predicate)


class Profiles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ───────────────────────── profile command group ─────────────────────────
    profile_group = app_commands.Group(
        name="profile",
        description="Set or view BDSM profiles",
        guild_only=True
    )

    @profile_group.command(name="view", description="View your own or someone else's profile")
    @app_commands.describe(user="The user whose profile to view (leave empty for your own)")
    async def profile_view(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        await self._show_profile(interaction, target)

    @profile_group.command(name="set", description="Set or clear your profile fields")
    @app_commands.describe(
        role="Dom, Sub, or Switch",
        clear_role="Remove your role",
        about="A short bio (max 500 chars)",
        clear_about="Remove your about text",
        limits="Your hard/soft limits (max 500 chars)",
        clear_limits="Remove your limits",
        experience="Your experience level (e.g. Beginner, 5 years, etc.)",
        clear_experience="Remove your experience"
    )
    async def profile_set(
        self,
        interaction: discord.Interaction,
        role: str = None,
        clear_role: bool = False,
        about: str = None,
        clear_about: bool = False,
        limits: str = None,
        clear_limits: bool = False,
        experience: str = None,
        clear_experience: bool = False,
    ):
        user_id = interaction.user.id

        # Validate role early
        if role is not None:
            role = role.strip().lower()
            if role not in ("dom", "sub", "switch"):
                await interaction.response.send_message(
                    "❌ Role must be 'Dom', 'Sub', or 'Switch'.", ephemeral=True
                )
                return
            role = role.capitalize()  # Store canonical form

        # Validate text lengths
        for field, value in [("about", about), ("limits", limits)]:
            if value is not None and len(value) > 500:
                await interaction.response.send_message(
                    f"❌ {field.capitalize()} cannot exceed 500 characters.", ephemeral=True
                )
                return

        # Build SQL update dynamically
        updates = {}
        if clear_role:
            updates["role"] = None
        elif role is not None:
            updates["role"] = role

        if clear_about:
            updates["about"] = None
        elif about is not None:
            updates["about"] = about

        if clear_limits:
            updates["limits"] = None
        elif limits is not None:
            updates["limits"] = limits

        if clear_experience:
            updates["experience"] = None
        elif experience is not None:
            updates["experience"] = experience

        if not updates:
            await interaction.response.send_message(
                "❌ You didn't provide anything to update. Use the options to set or clear fields.",
                ephemeral=True
            )
            return

        try:
            async with self.bot.db_pool.acquire() as conn:
                # Upsert: insert if not exists, then update provided fields
                await conn.execute(
                    """
                    INSERT INTO profiles (user_id, role, about, limits, experience)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (user_id) DO UPDATE SET
                        role = COALESCE($6, profiles.role),
                        about = COALESCE($7, profiles.about),
                        limits = COALESCE($8, profiles.limits),
                        experience = COALESCE($9, profiles.experience)
                    """,
                    user_id,
                    updates.get("role"),
                    updates.get("about"),
                    updates.get("limits"),
                    updates.get("experience"),
                    updates.get("role"),
                    updates.get("about"),
                    updates.get("limits"),
                    updates.get("experience"),
                )
            await interaction.response.send_message(
                "✅ Your profile has been updated.", ephemeral=True
            )
            logger.info(
                "Profile updated for %s: fields=%s",
                interaction.user, list(updates.keys())
            )
        except Exception as e:
            logger.error("Profile update error for %s: %s", interaction.user, e)
            await interaction.response.send_message(
                "❌ Database error. Please try again later.", ephemeral=True
            )

    async def _show_profile(self, interaction: discord.Interaction, user: discord.Member):
        """Internal helper to fetch and display a user's profile."""
        try:
            async with self.bot.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT role, about, limits, experience FROM profiles WHERE user_id = $1",
                    user.id
                )
                if not row:
                    if user == interaction.user:
                        msg = "❌ You haven't set a profile yet. Use `/profile set` to create one."
                    else:
                        msg = f"❌ {user.display_name} hasn't set a profile yet."
                    await interaction.response.send_message(msg, ephemeral=True)
                    return

                embed = discord.Embed(
                    title=user.display_name,
                    description=row["about"] or "*No bio set.*",
                    color=0xDC2626,
                    timestamp=discord.utils.utcnow()
                )
                embed.set_thumbnail(url=user.display_avatar.url)

                # Inline fields for role, experience, limits
                embed.add_field(name="Role", value=row["role"] or "Not specified", inline=True)
                embed.add_field(name="Experience", value=row["experience"] or "Not specified", inline=True)
                embed.add_field(name="Limits", value=row["limits"] or "Not specified", inline=False)
                embed.set_footer(text=f"Requested by {interaction.user.display_name}")

                await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error("Profile view error for %s: %s", user, e)
            await interaction.response.send_message(
                "❌ Database error. Please try again later.", ephemeral=True
            )

    # ───────────────────────── kinklist command group ─────────────────────────
    kinklist_group = app_commands.Group(
        name="kinklist",
        description="Manage your kink list",
        guild_only=True
    )

    @kinklist_group.command(name="view", description="View your own or someone else's kink list")
    @app_commands.describe(user="The user whose kink list to view (leave empty for your own)")
    async def kinklist_view(self, interaction: discord.Interaction, user: discord.Member = None):
        target = user or interaction.user
        await self._show_kinklist(interaction, target)

    @kinklist_group.command(name="add", description="Add one or more kinks (comma-separated)")
    @app_commands.describe(kinks="Comma-separated kinks (each max 50 chars, total max 20)")
    async def kinklist_add(self, interaction: discord.Interaction, kinks: str):
        await self._modify_kinks(interaction, kinks, mode="add")

    @kinklist_group.command(name="remove", description="Remove one or more kinks")
    @app_commands.describe(kinks="Comma-separated kinks to remove")
    async def kinklist_remove(self, interaction: discord.Interaction, kinks: str):
        await self._modify_kinks(interaction, kinks, mode="remove")

    @kinklist_group.command(name="clear", description="Remove all your kinks")
    async def kinklist_clear(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        try:
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute("DELETE FROM kinklists WHERE user_id = $1", user_id)
            await interaction.response.send_message(
                "✅ Your kink list has been cleared.", ephemeral=True
            )
        except Exception as e:
            logger.error("Kinklist clear error for %s: %s", interaction.user, e)
            await interaction.response.send_message(
                "❌ Database error. Please try again later.", ephemeral=True
            )

    @kinklist_group.command(name="compare", description="Compare your kinks with another user")
    @app_commands.describe(user="The user to compare with")
    async def kinklist_compare(self, interaction: discord.Interaction, user: discord.Member):
        my_id = interaction.user.id
        their_id = user.id

        try:
            async with self.bot.db_pool.acquire() as conn:
                my_row = await conn.fetchrow(
                    "SELECT kinks FROM kinklists WHERE user_id = $1", my_id
                )
                their_row = await conn.fetchrow(
                    "SELECT kinks FROM kinklists WHERE user_id = $1", their_id
                )

            my_kinks = set(my_row["kinks"]) if my_row and my_row["kinks"] else set()
            their_kinks = set(their_row["kinks"]) if their_row and their_row["kinks"] else set()

            if not my_kinks and not their_kinks:
                await interaction.response.send_message("Neither of you have any kinks listed.", ephemeral=True)
                return

            shared = my_kinks.intersection(their_kinks)
            only_mine = my_kinks - their_kinks
            only_theirs = their_kinks - my_kinks

            embed = discord.Embed(
                title=f"Kink Compatibility: {interaction.user.display_name} & {user.display_name}",
                color=0xDC2626,
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(
                name="💞 Shared Kinks",
                value=", ".join(sorted(shared)) if shared else "None",
                inline=False
            )
            embed.add_field(
                name=f"👤 Only {interaction.user.display_name}",
                value=", ".join(sorted(only_mine)) if only_mine else "None",
                inline=True
            )
            embed.add_field(
                name=f"👤 Only {user.display_name}",
                value=", ".join(sorted(only_theirs)) if only_theirs else "None",
                inline=True
            )
            embed.set_footer(text="Kink compatibility is just for fun – always negotiate!")

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error("Kinklist compare error for %s & %s: %s", interaction.user, user, e)
            await interaction.response.send_message(
                "❌ Database error. Please try again later.", ephemeral=True
            )

    # ─────────────────────── internal helpers ───────────────────────
    async def _show_kinklist(self, interaction: discord.Interaction, user: discord.Member):
        try:
            async with self.bot.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT kinks FROM kinklists WHERE user_id = $1", user.id
                )
                if not row or not row["kinks"]:
                    if user == interaction.user:
                        msg = "❌ You haven't set any kinks yet. Use `/kinklist add` to add some."
                    else:
                        msg = f"❌ {user.display_name} hasn't set any kinks yet."
                    await interaction.response.send_message(msg, ephemeral=True)
                    return

                kinks = row["kinks"]
                # Paginate if too many? For now a simple embed
                desc = ", ".join(kinks)
                if len(desc) > 2048:
                    # Truncate with warning
                    desc = desc[:2044] + "…"

                embed = discord.Embed(
                    title=f"{user.display_name}'s Kink List",
                    description=desc,
                    color=0xDC2626,
                    timestamp=discord.utils.utcnow()
                )
                embed.set_footer(text=f"{len(kinks)} kinks | Use /kinklist add/remove to edit")
                await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error("Kinklist view error for %s: %s", user, e)
            await interaction.response.send_message(
                "❌ Database error. Please try again later.", ephemeral=True
            )

    async def _modify_kinks(self, interaction: discord.Interaction, kinks_str: str, mode: str):
        """Add or remove kinks from a user's list."""
        new_items = [k.strip().lower() for k in kinks_str.split(",") if k.strip()]
        if not new_items:
            await interaction.response.send_message(
                "❌ Please provide at least one valid kink.", ephemeral=True
            )
            return

        # Validate lengths
        for k in new_items:
            if len(k) > 50:
                await interaction.response.send_message(
                    f"❌ Kink `{k[:30]}…` exceeds 50 characters.", ephemeral=True
                )
                return

        user_id = interaction.user.id

        try:
            async with self.bot.db_pool.acquire() as conn:
                # Fetch current kinks
                row = await conn.fetchrow(
                    "SELECT kinks FROM kinklists WHERE user_id = $1", user_id
                )
                current = row["kinks"] if row and row["kinks"] else []

                if mode == "add":
                    # Add unique new items, cap at 20
                    current_set = set(current)
                    added = 0
                    for k in new_items:
                        if k not in current_set and len(current_set) < 20:
                            current_set.add(k)
                            added += 1
                    if added == 0:
                        await interaction.response.send_message(
                            "❌ No new kinks added. Either they were already in your list or your list is full (max 20).",
                            ephemeral=True
                        )
                        return
                    updated = list(current_set)
                    action_msg = f"Added {added} kink(s)."
                else:  # remove
                    # Remove only those that exist
                    current_set = set(current)
                    removed = 0
                    for k in new_items:
                        if k in current_set:
                            current_set.discard(k)
                            removed += 1
                    if removed == 0:
                        await interaction.response.send_message(
                            "❌ None of those kinks were in your list.", ephemeral=True
                        )
                        return
                    updated = list(current_set)
                    action_msg = f"Removed {removed} kink(s)."

                # Save updated list
                await conn.execute(
                    """
                    INSERT INTO kinklists (user_id, kinks) VALUES ($1, $2)
                    ON CONFLICT (user_id) DO UPDATE SET kinks = $2, updated_at = NOW()
                    """,
                    user_id, updated
                )

            await interaction.response.send_message(
                f"✅ {action_msg}\n**Current list:** {', '.join(sorted(updated))}",
                ephemeral=True
            )
            logger.info(
                "Kinklist %s for %s: new=%s",
                mode, interaction.user, new_items
            )

        except Exception as e:
            logger.error("Kinklist modify error for %s: %s", interaction.user, e)
            await interaction.response.send_message(
                "❌ Database error. Please try again later.", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Profiles(bot))
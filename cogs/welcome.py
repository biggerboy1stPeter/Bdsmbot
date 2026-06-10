import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger("kinkbot")

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Create verification channel and send welcome message."""
        guild = member.guild

        # ── Fetch settings ──
        welcome_channel_id = await self._get_setting(guild.id, "welcome_channel_id")
        verification_category_id = await self._get_setting(guild.id, "verification_category_id")
        verified_role_id = await self._get_setting(guild.id, "verified_role_id")
        admin_role_id = await self._get_setting(guild.id, "admin_role_id")  # from server config

        # 1) Send welcome embed in the welcome channel
        if welcome_channel_id:
            channel = guild.get_channel(int(welcome_channel_id))
            if channel and isinstance(channel, discord.TextChannel):
                embed = discord.Embed(
                    title=f"Welcome to {guild.name}, {member.display_name}!",
                    description=(
                        "We're thrilled to have you here.\n\n"
                        "**To get started, please set up your profile** using `/profile set`.\n"
                        "Once you're done, an admin will verify you and give you access to the full server."
                    ),
                    color=0xDC2626
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text="BDSM Collective • Safe, sane, consensual")
                try:
                    await channel.send(content=member.mention, embed=embed)
                except Exception as e:
                    logger.error(f"Could not send welcome message in {guild.name}: {e}")

        # 2) Create verification channel
        if verification_category_id:
            category = guild.get_channel(int(verification_category_id))
            if not category or not isinstance(category, discord.CategoryChannel):
                logger.warning(f"Verification category not found in {guild.name}")
                return
        else:
            # If no category set, skip channel creation
            return

        # Build channel name
        safe_name = member.name.replace(' ', '-').lower()
        channel_name = f"🔐-verify-{safe_name}"[:100]

        # Permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_permissions=True
            )
        }
        # Add admin role(s) if configured
        if admin_role_id:
            admin_role = guild.get_role(int(admin_role_id))
            if admin_role:
                overwrites[admin_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )
        # Also add any role with administrator permission? Not necessary.

        try:
            verify_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Verification channel for {member}"
            )
        except discord.Forbidden:
            logger.error(f"Missing permissions to create channel in {guild.name}")
            return
        except Exception as e:
            logger.error(f"Failed to create verification channel: {e}")
            return

        # Send instructions in the new channel
        embed = discord.Embed(
            title="🔐 Verification Required",
            description=(
                f"Welcome {member.mention}!\n\n"
                "To gain access to the server, please complete your profile using `/profile set`.\n\n"
                "**Once done, wait for an admin to verify you.**\n"
                "They will assign you the verified role and close this channel."
            ),
            color=0xDC2626
        )
        embed.set_footer(text="BDSM Collective • Verification process")
        try:
            await verify_channel.send(content=member.mention, embed=embed)
        except Exception:
            pass

    # ── Helper: get a setting ──
    async def _get_setting(self, guild_id, key, default=None):
        try:
            async with self.bot.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT value FROM configs WHERE guild_id=$1 AND key=$2",
                    guild_id, key
                )
                return row['value'] if row else default
        except Exception as e:
            logger.error(f"DB error in get_setting for {key}: {e}")
            return default

    # ── /verify command ──
    @app_commands.command(name="verify", description="Verify a member and grant them the verified role")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.describe(member="The member to verify", reason="Optional reason")
    async def verify_member(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        """Assign the verified role to a member and close their verification channel."""
        await interaction.response.defer(ephemeral=True)

        verified_role_id = await self._get_setting(interaction.guild_id, "verified_role_id")
        if not verified_role_id:
            await interaction.followup.send("❌ Verified role is not configured.", ephemeral=True)
            return

        role = interaction.guild.get_role(int(verified_role_id))
        if not role:
            await interaction.followup.send("❌ Verified role not found.", ephemeral=True)
            return

        # Check if already verified
        if role in member.roles:
            await interaction.followup.send(f"ℹ️ {member.mention} is already verified.", ephemeral=True)
            # Still try to close their verification channel if exists
            await self._close_verification_channel(member, interaction)
            return

        try:
            await member.add_roles(role, reason=f"Verified by {interaction.user} - {reason or 'No reason'}")
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to assign that role.", ephemeral=True)
            return
        except Exception as e:
            logger.error(f"Error assigning verified role: {e}")
            await interaction.followup.send("❌ Failed to assign the role.", ephemeral=True)
            return

        # Send closure message in verification channel
        closed = await self._close_verification_channel(member, interaction)

        await interaction.followup.send(
            f"✅ Verified {member.mention} and assigned {role.mention}." +
            (" Channel closed." if closed else ""),
            ephemeral=True
        )

    async def _close_verification_channel(self, member: discord.Member, interaction: discord.Interaction):
        """Find the user's verification channel, send a goodbye message, and delete it."""
        guild = member.guild
        safe_name = member.name.replace(' ', '-').lower()
        target_name = f"🔐-verify-{safe_name}"[:100]

        for channel in guild.text_channels:
            if channel.name.startswith("🔐-verify-") and member in channel.overwrites:
                try:
                    embed = discord.Embed(
                        title="✅ Verified!",
                        description=(
                            f"{member.mention} has been verified.\n"
                            "This channel will be deleted in 10 seconds."
                        ),
                        color=0x00FF00
                    )
                    await channel.send(embed=embed)
                    await asyncio.sleep(10)
                    await channel.delete(reason="User verified")
                    return True
                except Exception as e:
                    logger.error(f"Error closing verification channel: {e}")
        return False


async def setup(bot):
    await bot.add_cog(Welcome(bot))

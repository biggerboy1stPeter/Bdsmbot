import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import os

class Orders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="order", description="Check your shop order status")
    async def order(self, interaction: discord.Interaction, order_id: str):
        base = os.getenv("SERVER_URL", "").rstrip("/")
        if not base:
            await interaction.response.send_message("⚠️ Shop server not configured.", ephemeral=True)
            return
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{base}/api/order/{order_id}") as resp:
                    if resp.status == 404:
                        await interaction.response.send_message("Order not found.")
                        return
                    data = await resp.json()
            except Exception:
                await interaction.response.send_message("⚠️ Could not contact shop server.")
                return
        embed = discord.Embed(title=f"Order {order_id}", color=0xdc2626)
        embed.add_field(name="Status", value=data.get("status","unknown"))
        embed.add_field(name="Total", value=f"${data.get('amount',0)}")
        items = data.get("cart", [])
        item_str = "\n".join([f"{i['qty']}x {i['name']}" for i in items]) or "None"
        embed.add_field(name="Items", value=item_str, inline=False)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Orders(bot))

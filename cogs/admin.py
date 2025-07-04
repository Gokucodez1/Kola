import discord
from discord.ext import commands
from utils import send_ltc, validate_ltc_address
import sqlite3

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conn = sqlite3.connect('deals.db', check_same_thread=False)

    @commands.command()
    @commands.is_owner()
    async def release(self, ctx, channel_id: int, ltc_address: str):
        """Force release funds (Owner Only)"""
        if not validate_ltc_address(ltc_address):
            return await ctx.send("❌ Invalid LTC address!")
            
        try:
            cursor = self.conn.cursor()
            deal = cursor.execute(
                "SELECT amount_ltc, deal_code FROM deals WHERE channel_id=?",
                (channel_id,)
            ).fetchone()
            
            if not deal:
                return await ctx.send("❌ Deal not found!")
                
            txid = send_ltc(ltc_address, deal[0])
            
            embed = discord.Embed(
                title="⚡ Owner Override",
                description=(
                    f"**Deal Code:** `{deal[1]}`\n"
                    f"**Amount:** {deal[0]:.8f} LTC\n"
                    f"**To:** `{ltc_address}`\n"
                    f"**TXID:** `{txid}`"
                ),
                color=0xe74c3c
            )
            
            await ctx.send(embed=embed)
            cursor.execute(
                "UPDATE deals SET status='completed' WHERE channel_id=?",
                (channel_id,)
            )
            self.conn.commit()
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")

    @commands.command()
    @commands.is_owner()
    async def cancel(self, ctx, channel_id: int):
        """Cancel a deal (Owner Only)"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE deals SET status='cancelled' WHERE channel_id=?",
                (channel_id,)
            )
            self.conn.commit()
            await ctx.send(f"✅ Deal in <#{channel_id}> cancelled")
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")

async def setup(bot):
    await bot.add_cog(Admin(bot))

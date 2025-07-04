import discord
from discord.ext import commands, tasks
from utils import validate_ltc_address, send_ltc, log_error
from sochain import check_payment
import sqlite3

class Monitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conn = sqlite3.connect('deals.db', check_same_thread=False)
        self.check_payments.start()

    @tasks.loop(seconds=30)
    async def check_payments(self):
        cursor = self.conn.cursor()
        try:
            deals = cursor.execute("""
                SELECT channel_id, amount_ltc, deal_code 
                FROM deals 
                WHERE status='amount_set'
            """).fetchall()
            
            for channel_id, amount_ltc, deal_code in deals:
                payment = check_payment(amount_ltc)
                if payment:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        await self.process_payment(channel, payment, amount_ltc, deal_code)
                        
        except Exception as e:
            await log_error(None, f"Payment check error: {e}")

    async def process_payment(self, channel, payment, amount_ltc, deal_code):
        try:
            embed = discord.Embed(
                title="💰 Payment Received",
                description=(
                    f"**Deal Code:** `{deal_code}`\n"
                    f"**Amount:** {amount_ltc:.8f} LTC\n"
                    f"**TXID:** `{payment['txid']}`\n"
                    f"**Confirmations:** {payment['confirmations']}/6"
                ),
                color=0x2ecc71
            )
            
            if payment['confirmations'] >= 6:
                embed.add_field(
                    name="✅ Fully Confirmed",
                    value="Funds can now be released",
                    inline=False
                )
                
            await channel.send(
                embed=embed,
                view=self.ReleaseView(channel.id)
            )
            
            if payment['confirmations'] >= 6:
                cursor = self.conn.cursor()
                cursor.execute(
                    "UPDATE deals SET status='paid' WHERE channel_id=?",
                    (channel.id,)
                )
                self.conn.commit()
                
        except Exception as e:
            await log_error(channel, f"Payment processing failed: {e}")

    class ReleaseView(discord.ui.View):
        def __init__(self, channel_id):
            super().__init__(timeout=None)
            self.channel_id = channel_id

        @discord.ui.button(label="Release Funds", style=discord.ButtonStyle.green)
        async def release(self, interaction, button):
            await interaction.response.send_modal(
                self.ReleaseModal(self.channel_id)
            )

    class ReleaseModal(discord.ui.Modal):
        def __init__(self, channel_id):
            super().__init__(title="Fund Release")
            self.channel_id = channel_id
            self.address = discord.ui.TextInput(
                label="Recipient LTC Address",
                placeholder="L...",
                max_length=34
            )
            self.add_item(self.address)

        async def on_submit(self, interaction):
            if not validate_ltc_address(self.address.value):
                return await interaction.response.send_message(
                    "❌ Invalid LTC address format!",
                    ephemeral=True
                )
                
            try:
                cursor = self.conn.cursor()
                deal = cursor.execute(
                    "SELECT amount_ltc FROM deals WHERE channel_id=?",
                    (self.channel_id,)
                ).fetchone()
                
                txid = send_ltc(self.address.value, deal[0])
                
                await interaction.response.send_message(
                    f"✅ Funds released! TXID: `{txid}`",
                    ephemeral=True
                )
                
                cursor.execute(
                    "UPDATE deals SET status='completed' WHERE channel_id=?",
                    (self.channel_id,)
                )
                self.conn.commit()
                
            except Exception as e:
                await log_error(interaction.channel, f"Fund release failed: {e}")

async def setup(bot):
    await bot.add_cog(Monitor(bot))

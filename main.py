import discord
from discord.ext import commands
from discord import ui, ButtonStyle, Embed
import asyncio
import json
from utils import *
from sochain import check_payment

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)  # Prefix not used but required

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.load_extension('cogs.rates')

@bot.event
async def on_guild_channel_create(channel):
    if channel.category_id == int(bot.config['deal_category_id']):
        deal_code = generate_deal_code()
        msg = await channel.send(
            embed=discord.Embed(
                title="NEW DEAL CHANNEL",
                description=(
                    f"Deal Code: `{deal_code}`\n\n"
                    "Please send the **Developer ID** of the user you're trading with.\n"
                    "Type `cancel` to abort this deal."
                ),
                color=0x5865F2
            )
        )

        def check(m):
            return (
                m.channel == channel and 
                m.author != bot.user and
                (m.content.lower() == 'cancel' or m.content.strip().isdigit())
            )

        try:
            msg = await bot.wait_for('message', check=check, timeout=300)
            if msg.content.lower() == 'cancel':
                return await channel.delete()
            
            user_id = int(msg.content.strip())
            user = await bot.fetch_user(user_id)
            await channel.set_permissions(user, read_messages=True, send_messages=True)
            
            cursor.execute(
                "INSERT INTO deals VALUES (?, ?, ?, ?, ?, ?, ?)",
                (channel.id, deal_code, msg.author.id, user_id, None, None, 'init')
            )
            conn.commit()
            
            await channel.send(
                embed=discord.Embed(
                    title="DEAL PARTNER ADDED",
                    description=f"<@{user_id}> can now participate in this deal",
                    color=0x00FF00
                ),
                view=RoleView(channel.id)
            )
            
        except (asyncio.TimeoutError, ValueError):
            await channel.delete()

class RoleView(ui.View):
    def __init__(self, channel_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    @ui.button(label="I'm Sending LTC", style=ButtonStyle.green)
    async def sender(self, interaction, button):
        deal = cursor.execute("SELECT * FROM deals WHERE channel_id=?", (self.channel_id,)).fetchone()
        if not deal:
            return await interaction.response.send_message("Deal expired!", ephemeral=True)
        
        cursor.execute(
            "UPDATE deals SET sender_id=? WHERE channel_id=?",
            (interaction.user.id, self.channel_id)
        )
        conn.commit()
        await interaction.response.send_message(
            embed=discord.Embed(
                description="✅ You are now the **LTC Sender**",
                color=0x00FF00
            ),
            ephemeral=True
        )
        await check_roles_ready(interaction.channel)

    @ui.button(label="I'm Receiving LTC", style=ButtonStyle.blurple)
    async def receiver(self, interaction, button):
        deal = cursor.execute("SELECT * FROM deals WHERE channel_id=?", (self.channel_id,)).fetchone()
        if not deal:
            return await interaction.response.send_message("Deal expired!", ephemeral=True)
        
        cursor.execute(
            "UPDATE deals SET receiver_id=? WHERE channel_id=?",
            (interaction.user.id, self.channel_id)
        )
        conn.commit()
        await interaction.response.send_message(
            embed=discord.Embed(
                description="✅ You are now the **LTC Receiver**",
                color=0x00FF00
            ),
            ephemeral=True
        )
        await check_roles_ready(interaction.channel)

async def check_roles_ready(channel):
    deal = cursor.execute("SELECT * FROM deals WHERE channel_id=?", (channel.id,)).fetchone()
    if deal and deal[2] and deal[3]:  # Both roles assigned
        await channel.send(
            embed=discord.Embed(
                title="ROLES CONFIRMED",
                description=(
                    f"**Sender:** <@{deal[2]}>\n"
                    f"**Receiver:** <@{deal[3]}>\n\n"
                    "Please enter the USD amount for this deal:"
                ),
                color=0x5865F2
            )
        )

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
        
    deal = cursor.execute("SELECT * FROM deals WHERE channel_id=?", (message.channel.id,)).fetchone()
    if deal and deal[6] == 'init' and message.content.replace('$', '').replace('.', '').isdigit():
        amount = float(message.content.replace('$', ''))
        if amount < 0.1:
            return await message.channel.send("Minimum amount is $0.10")
            
        ltc_amount = amount / get_live_rate()
        cursor.execute(
            "UPDATE deals SET amount_usd=?, amount_ltc=?, status='amount_set' WHERE channel_id=?",
            (amount, ltc_amount, message.channel.id)
        )
        conn.commit()
        
        await message.channel.send(
            embed=discord.Embed(
                title="PAYMENT INVOICE",
                description=(
                    f"**Amount:** ${amount:.2f} USD\n"
                    f"**Equivalent:** {ltc_amount:.8f} LTC\n\n"
                    f"Send exactly `{ltc_amount:.8f} LTC` to:\n"
                    f"`{get_ltc_address()}`"
                ),
                color=0x00FF00
            ),
            view=InvoiceView()
        )

class InvoiceView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @ui.button(label="Show Address", style=ButtonStyle.green)
    async def address(self, interaction, button):
        await interaction.response.send_message(
            f"```{get_ltc_address()}```",
            ephemeral=False
        )
    
    @ui.button(label="QR Code", style=ButtonStyle.blurple)
    async def qr(self, interaction, button):
        with open('qr.txt') as f:
            qr = f.read().strip()
        await interaction.response.send_message(
            f"QR Code: {qr}",
            ephemeral=False
        )

@tasks.loop(seconds=30)
async def check_payments():
    deals = cursor.execute("SELECT channel_id, amount_ltc FROM deals WHERE status='amount_set'").fetchall()
    for channel_id, amount_ltc in deals:
        payment = check_payment(amount_ltc)
        if payment:
            channel = bot.get_channel(channel_id)
            await channel.send(
                embed=discord.Embed(
                    title="PAYMENT RECEIVED",
                    description=(
                        f"**Amount:** {amount_ltc:.8f} LTC\n"
                        f"**TXID:** `{payment['txid']}`\n"
                        f"**Confirmations:** {payment['confirmations']}/6"
                    ),
                    color=0x00FF00
                ),
                view=ReleaseView(channel_id)
            )
            cursor.execute(
                "UPDATE deals SET status='paid' WHERE channel_id=?",
                (channel_id,)
            )
            conn.commit()

class ReleaseView(ui.View):
    def __init__(self, channel_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    @ui.button(label="Release Funds", style=ButtonStyle.green)
    async def release(self, interaction, button):
        deal = cursor.execute("SELECT * FROM deals WHERE channel_id=?", (self.channel_id,)).fetchone()
        if not deal:
            return await interaction.response.send_message("Deal expired!", ephemeral=True)
            
        if interaction.user.id != deal[2]:  # Only sender can release
            return await interaction.response.send_message("Only the sender can release funds!", ephemeral=True)
            
        await interaction.response.send_modal(ReleaseModal(self.channel_id))

class ReleaseModal(ui.Modal):
    def __init__(self, channel_id):
        super().__init__(title="Release Funds")
        self.channel_id = channel_id
        self.address = ui.TextInput(label="Receiver LTC Address", placeholder="L...")
        self.add_item(self.address)
    
    async def on_submit(self, interaction):
        if not validate_ltc_address(self.address.value):
            return await interaction.response.send_message("Invalid LTC address!", ephemeral=True)
            
        deal = cursor.execute("SELECT * FROM deals WHERE channel_id=?", (self.channel_id,)).fetchone()
        txid = send_ltc(self.address.value, deal[4])
        
        await interaction.channel.send(
            embed=discord.Embed(
                title="FUNDS RELEASED",
                description=(
                    f"**Amount:** {deal[4]:.8f} LTC\n"
                    f"**To Address:** `{self.address.value}`\n"
                    f"**TXID:** `{txid}`"
                ),
                color=0x00FF00
            )
        )
        cursor.execute(
            "UPDATE deals SET status='completed' WHERE channel_id=?",
            (self.channel_id,)
        )
        conn.commit()
        await interaction.response.defer()

@bot.command()
@commands.is_owner()
async def release(ctx, channel_id: int, ltc_address: str):
    """Owner override to release funds"""
    deal = cursor.execute("SELECT * FROM deals WHERE channel_id=?", (channel_id,)).fetchone()
    if not deal:
        return await ctx.send("Deal not found!")
        
    if not validate_ltc_address(ltc_address):
        return await ctx.send("Invalid LTC address!")
        
    txid = send_ltc(ltc_address, deal[4])
    await ctx.send(
        embed=discord.Embed(
            title="OWNER OVERRIDE: FUNDS RELEASED",
            description=(
                f"**Channel:** <#{channel_id}>\n"
                f"**Amount:** {deal[4]:.8f} LTC\n"
                f"**To:** `{ltc_address}`\n"
                f"**TXID:** `{txid}`"
            ),
            color=0xFFA500
        )
    )
    cursor.execute(
        "UPDATE deals SET status='completed' WHERE channel_id=?",
        (channel_id,)
    )
    conn.commit()

# Load config and start
with open('config.json') as f:
    bot.config = json.load(f)
check_payments.start()
bot.run(bot.config['bot_token'])

import discord
from discord.ext import commands, tasks
import requests
from datetime import datetime

class Rates(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_rate = 0
        self.update_rates.start()

    @tasks.loop(minutes=5)
    async def update_rates(self):
        try:
            response = requests.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd",
                timeout=10
            )
            rate = response.json()["litecoin"]["usd"]
            
            if rate != self.last_rate:
                channel = self.bot.get_channel(int(self.bot.config['rate_channel_id']))
                await channel.edit(topic=f"⏳ Last update: {datetime.utcnow().strftime('%H:%M UTC')}")
                embed = discord.Embed(
                    title="💱 LTC/USD Rate Update",
                    description=f"**1 LTC = ${rate:.2f}**",
                    color=0x3498db
                )
                await channel.send(embed=embed)
                self.last_rate = rate
        except Exception as e:
            print(f"Rate update failed: {e}")

    @update_rates.before_loop
    async def before_rates(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Rates(bot))

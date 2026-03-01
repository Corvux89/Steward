
from datetime import datetime, timezone
import logging

from discord.ext import commands, tasks

from Steward.bot import StewardBot
from Steward.models.objects.raffleHouse import Raffle

log = logging.getLogger(__name__)


def setup(bot: StewardBot):
    bot.add_cog(RaffleCog(bot))


class RaffleCog(commands.Cog):
    bot: StewardBot

    def __init__(self, bot: StewardBot):
        self.bot = bot
        log.info(f"Cog '{self.__cog_name__}' loaded")

    @commands.Cog.listener()
    async def on_db_connected(self):
        houses = await Raffle.fetch_all(self.bot)

        for house in houses:
            await house.refresh_view()

        self.market_loop.start()

    def cog_unload(self):
        self.market_loop.cancel()

    @tasks.loop(minutes=1)
    async def market_loop(self):
        houses = await Raffle.fetch_all(self.bot)
        now = datetime.now(timezone.utc)

        for house in houses:
            for inv in list(house.inventory):
                ending = house.raffle_end_at(inv)
                if ending and now >= ending:
                    await house.finalize_raffle(inv, "Raffle Ended")

            if not house.inventory:
                await house.reroll_inventory()
    
    @market_loop.before_loop
    async def before_market_loop(self):
        await self.bot.wait_until_ready()

from datetime import datetime, timezone
import logging

from discord.ext import commands, tasks

from Steward.bot import StewardBot
from Steward.models.objects.auctionHouse import AuctionHouse

log = logging.getLogger(__name__)


def setup(bot: StewardBot):
    bot.add_cog(AuctionHouseCog(bot))


class AuctionHouseCog(commands.Cog):
    bot: StewardBot

    def __init__(self, bot: StewardBot):
        self.bot = bot
        log.info(f"Cog '{self.__cog_name__}' loaded")

    @commands.Cog.listener()
    async def on_db_connected(self):
        houses = await AuctionHouse.fetch_all(self.bot)

        for house in houses:
            await house.refresh_view()

        self.market_loop.start()

    def cog_unload(self):
        self.market_loop.cancel()

    @tasks.loop(minutes=1)
    async def market_loop(self):
        houses = await AuctionHouse.fetch_all(self.bot)
        now = datetime.now(timezone.utc)

        for house in houses:
            for inv in list(house.inventory):
                ending = house.auction_end_at(inv)
                if ending and now >= ending:
                    await house.finalize_item(inv, "Auction Ended")

            reroll_at = house.next_reroll_at()

            if reroll_at and now >= reroll_at:
                await house.reroll_inventory()

            if not house.inventory and house.reroll_interval:
                await house.reroll_inventory()
    
    @market_loop.before_loop
    async def before_market_loop(self):
        await self.bot.wait_until_ready()
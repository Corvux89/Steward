import logging

from discord.ext import commands

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
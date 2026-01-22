import logging
import discord
from discord.ext import commands
from timeit import default_timer as timer


from Steward.bot import StewardBot
from Steward.utils.discordUtils import is_staff

log = logging.getLogger(__name__)


def setup(bot: StewardBot):
    bot.add_cog(RulesCog(bot))


class RulesCog(commands.Cog):
    bot: StewardBot
    
    def __init__(self, bot):
        self.bot = bot
        log.info(f"Cog '{self.__cog_name__}' loaded")
    

    @commands.Cog.listener()
    async def on_new_character(self, character, log_entry):
        here=1
        log.critical("HERE!")
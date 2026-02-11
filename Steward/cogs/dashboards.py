import logging
import discord

from discord.ext import commands
from Steward.bot import StewardBot
from Steward.models.objects.dashboards import CategoryDashboard


log = logging.getLogger(__name__)

def setup(bot: StewardBot):
    bot.add_cog(DashboardCog(bot))

class DashboardCog(commands.Cog):
    bot: StewardBot

    def __init__(self, bot):
        self.bot = bot
        log.info(f"Cog '{self.__cog_name__}' loaded")

    @commands.Cog.listener()
    async def on_db_connected(self):
        dashboards = await CategoryDashboard.fetch_all(self.bot)

        for dashboard in dashboards:
            await dashboard.refresh()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not hasattr(self.bot, "db"):
            return
        
        if hasattr(message.channel, "category_id") and isinstance(message.channel, discord.TextChannel):
            if (dashboards := await CategoryDashboard.fetch(self.bot, message.channel.category_id)):
                for dashboard in dashboards:
                    await dashboard.refresh(message)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not hasattr(self.bot, "db"):
            return
        
        if isinstance(channel, discord.CategoryChannel):
            if (dashboards := await CategoryDashboard.fetch(self.bot, channel.id)):
                for dashboard in dashboards:
                    await dashboard.delete()

    


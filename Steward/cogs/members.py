import logging
import discord
from discord.ext import commands

from Steward.bot import StewardBot, StewardContext
from Steward.models.objects.exceptions import CharacterNotFound, StewardCommandError
from Steward.models.views.player import PlayerInfoView
from Steward.models.objects.player import Player
from Steward.utils.discordUtils import is_admin, is_staff

log = logging.getLogger(__name__)


def setup(bot: StewardBot):
    bot.add_cog(MemberCog(bot))


class MemberCog(commands.Cog):
    bot: StewardBot

    def __init__(self, bot):
        self.bot = bot
        log.info(f"Cog '{self.__cog_name__}' loaded")

    @commands.user_command(name="Manage")
    @commands.check(is_staff)
    async def user_manage(self, ctx: StewardContext, member: discord.Member):
        player = await Player.get_or_create(self.bot.db, member)
        admin = is_admin(ctx)
        ui = PlayerInfoView(self.bot, ctx, player, staff=True, admin=admin)
        await ctx.send(view=ui)
        await ctx.delete()

    @commands.user_command(name="Info")
    async def user_info(self, ctx: StewardContext, member: discord.Member):
        player = await Player.get_or_create(self.bot.db, member)

        if not player.active_characters:
            raise CharacterNotFound(player)

        ui = PlayerInfoView(self.bot, ctx, player, delete=False)
        await ctx.send(view=ui)
        await ctx.delete()
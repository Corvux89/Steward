import logging
import discord
from discord.ext import commands

from Steward.bot import StewardApplicationContext, StewardBot
from Steward.models.objects.exceptions import CharacterNotFound, StewardError
from Steward.models.views.log import CreateLogView
from Steward.models.views.player import PlayerInfoView
from Steward.models.objects.player import Player
from Steward.utils.discordUtils import is_admin, is_staff
from Steward.utils.viewUitils import get_activity_select_option

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
    async def user_manage(self, ctx: StewardApplicationContext, member: discord.Member):
        player = await Player.get_or_create(self.bot.db, member)
        admin = is_admin(ctx)
        ui = PlayerInfoView(self.bot, ctx, player, staff=True, admin=admin)
        await ctx.send(view=ui)
        await ctx.delete()

    @commands.user_command(name="Create Log")
    @commands.check(is_staff)
    async def user_reward(self, ctx: StewardApplicationContext, member: discord.Member):
        if not ctx.server.activities:
            raise StewardError("No activites are setup for reward. Contact an admin.")
        elif not get_activity_select_option(ctx.server, None, None, admin=is_admin(ctx)):
            raise StewardError("No activities are setup for you to log.")
        
        player = await Player.get_or_create(self.bot.db, member)

        if not player.active_characters:
            raise CharacterNotFound(player)
        
        ui = CreateLogView(ctx.author, self.bot, player, ctx.server, is_admin(ctx))
        await ctx.send(view=ui)
        await ctx.delete()

    @commands.user_command(name="Info")
    async def user_info(self, ctx: StewardApplicationContext, member: discord.Member):
        player = await Player.get_or_create(self.bot.db, member)

        if not player.active_characters:
            raise CharacterNotFound(player)

        ui = PlayerInfoView(self.bot, ctx, player, delete=False)
        await ctx.send(view=ui)
        await ctx.delete()
import re
import discord
import logging

from discord.ext import commands
from Steward.bot import StewardBot, StewardContext
from Steward.models.modals.application import ApplicationModal
from Steward.models.modals.reward import RewardModal
from Steward.models.objects.application import Application, ApplicationTemplate
from Steward.models.objects.exceptions import CharacterNotFound, StewardError
from Steward.models.objects.player import Player
from Steward.models.objects.webhook import StewardWebhook
from Steward.models.views.player import PlayerInfoView
from Steward.models.views.request import BaseRequestReviewView, Requestview
from Steward.utils.autocompleteUtils import application_autocomplete, character_autocomplete
from Steward.utils.discordUtils import dm_check, is_admin, is_staff, try_delete


log = logging.getLogger(__name__)

def setup(bot: StewardBot):
    bot.add_cog(CharacterCog(bot))

class CharacterCog(commands.Cog):
    bot: StewardBot

    def __init__(self, bot):
        self.bot = bot
        log.info(f"Cog '{self.__cog_name__}' loaded")

    @commands.Cog.listener()
    async def on_db_connected(self):
        self.bot.add_view(BaseRequestReviewView.new(self.bot))

    character_admin_commands = discord.SlashCommandGroup(
        "character_admin",
        "Character administration commands",
        contexts=[discord.InteractionContextType.guild]
    )

    @commands.command(name="say", contexts=[discord.InteractionContextType.guild])
    @commands.check(dm_check)
    async def character_say(self, ctx: StewardContext):
        await StewardWebhook(ctx).send()
        await try_delete(ctx.message)

    @character_admin_commands.command(
            name="manage",
            description="Manage a player's information"
    )
    @commands.check(is_staff)
    async def player_manage(self,
                            ctx: "StewardContext",
                            member: discord.Option(
                                discord.SlashCommandOptionType(6),
                                description="Player to manage",
                                required=True
                            )):
        player = await Player.get_or_create(self.bot.db, member)
        admin = is_admin(ctx)

        ui = PlayerInfoView(self.bot, ctx, player, staff=True, admin=admin)
        await ctx.send(view=ui)
        await ctx.delete()

    @character_admin_commands.command(
            name="reward",
            description="Give a player an activity reward"
    )
    async def player_reward(self,
                            ctx: "StewardContext",
                            member: discord.Option(
                                discord.SlashCommandOptionType(6),
                                description="Player to reward",
                                required=True
                            )
                            ):
        if not ctx.server.activities:
            raise StewardError("No activities are setup for reward. Contact an admin.")
        
        player = await Player.get_or_create(self.bot.db, member)
        
        if not player.active_characters:
            raise CharacterNotFound(player)

        modal = RewardModal(self.bot, player, ctx.server)
        await ctx.send_modal(modal)       


    @commands.slash_command(
        name="info",
        description="Displays information for a player"
        )
    async def player_info(self,
                          ctx: "StewardContext",
                          member: discord.Option(
                              discord.SlashCommandOptionType(6),
                              description="Player to view. Defaults to the person running the command.",
                              required=False
                          )
                        ):
        player = (
            ctx.player if not member else await Player.get_or_create(self.bot.db, member)
        )

        if not player.active_characters:
            raise CharacterNotFound(player)


        ui = PlayerInfoView(self.bot, ctx, player, delete=False)
        await ctx.send(view=ui)
        await ctx.delete()

    @commands.slash_command(
        name="submit",
        description="Make a request"
    )
    async def staff_request(
        self,
        ctx: "StewardContext",
        character: discord.Option(
            str,
            description="Character to request for",
            autocomplete=character_autocomplete
        ),
    ):
        character = next(
            (c for c in ctx.player.active_characters if c.name == character),
            None
        )

        if not character:
            raise CharacterNotFound(ctx.player)
        
        ui = Requestview(self.bot, ctx, ctx.player, character)
        await ctx.send(view=ui)
        await ctx.delete()

    @commands.slash_command(
        name="apply",
        description="Apply for something"
    )
    async def application(
        self,
        ctx: "StewardContext",
        application: discord.Option(
            str,
            description="What are you applying for?",
            autocomplete=application_autocomplete
        )
    ):
        template = await ApplicationTemplate.fetch(self.bot.db, ctx.server.id, application)

        if not template:
            raise StewardError("Cannot find application template")
        
        modal = ApplicationModal(self.bot, ctx.player, template)
        await ctx.send_modal(modal)

    # TODO: At some point this needs to handle the chunks that could come out of the initial application
    @commands.slash_command(
        name="edit_application",
        description="Edit your application"
    )
    async def edit_application(
        self, 
        ctx: "StewardContext"
    ):
        if not isinstance(ctx.channel, discord.Thread):
            raise StewardError("Application not found")
        
        first_message = await ctx.channel.parent.fetch_message(ctx.channel.id)

        if not first_message.author.bot:
            raise StewardError("This isn't an application thread")
        
        match = re.match(f'^\*+(.+?)\*+', first_message.content)
        if not match:
            raise StewardError("Application type not found")

        application_type = match.group(1)

        if not application_type:
            raise StewardError("Application type not found")
        
        if not (template := await ApplicationTemplate.fetch(self.bot.db, ctx.server.id, application_type)):
            raise StewardError("Application not found")
        
        if not first_message.mentions or  ctx.author != first_message.mentions[0]:
            raise StewardError("You don't own this application")
        
        character = None
        if template.character_specific == True:
            character = next(
                (c for c in ctx.player.active_characters if c.name == first_message.author.name),
                None
            )

        # Strip out the added header
        app_content = first_message.content.split('\n\n',1)[1]
        
        application = Application(
            ctx.player,
            template,
            character=character,
            content=app_content
        )

        modal = ApplicationModal(self.bot, ctx.player, template, application=application, message=first_message)

        await ctx.send_modal(modal)
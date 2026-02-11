import discord
import logging

from discord.ext import commands
from Steward.bot import StewardApplicationContext, StewardBot, StewardContext
from Steward.models.objects.request import Request
from Steward.models.views import confirm_view
from Steward.models.objects.form import Application, FormTemplate
from Steward.models.objects.exceptions import CharacterNotFound, StewardError
from Steward.models.objects.character import Character
from Steward.models.objects.player import Player
from Steward.models.objects.webhook import StewardWebhook
from Steward.models.views.log import CreateLogView
from Steward.models.views.player import PlayerInfoView
from Steward.models.views.request import PlayerRequestView, StaffRequestView, Requestview
from Steward.utils.autocompleteUtils import form_autocomplete, character_autocomplete
from Steward.utils.discordUtils import dm_check, is_admin, is_staff, try_delete
from Steward.utils.viewUitils import get_activity_select_option


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
        requests = await Request.fetch_all(self.bot)
        for request in requests:
            refresh = True if request.staff_message and request.player_message else False

            if refresh:
                staff_view = StaffRequestView(self.bot, request=request)
                player_view = PlayerRequestView(self.bot, request=request)

                try:
                    await request.staff_message.edit(view=staff_view)
                    await request.player_message.edit(view=player_view)
                except:
                    pass
            else:
                await request.delete()


    character_admin_commands = discord.SlashCommandGroup(
        "character_admin",
        "Character administration commands",
        contexts=[discord.InteractionContextType.guild]
    )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if (request := await Request.fetch(self.bot, message.id)):
            await request.delete()

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        if (application := await Application.fetch_by_message_id(self.bot.db, thread.guild.id, thread.id)):
            await application.delete()

    @commands.command(name="say", contexts=[discord.InteractionContextType.guild], aliases=['s'])
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
                            ctx: "StewardApplicationContext",
                            member: discord.Option(
                                discord.SlashCommandOptionType(6),
                                description="Player to manage",
                                required=True
                            )):
        player = await Player.get_or_create(self.bot.db, member)
        admin = is_admin(ctx)

        ui = PlayerInfoView(self.bot, ctx, player, staff=True, admin=admin)
        await ctx.send(view=ui, allowed_mentions=discord.AllowedMentions(users=False, roles=False))
        await ctx.delete()

    @character_admin_commands.command(
            name="create_log",
            description="Give a player an activity reward"
    )
    async def player_reward(self,
                            ctx: "StewardApplicationContext",
                            member: discord.Option(
                                discord.SlashCommandOptionType(6),
                                description="Player to reward",
                                required=True
                            )
                            ):
        if not ctx.server.activities:
            raise StewardError("No activities are setup for reward. Contact an admin.")
        elif not get_activity_select_option(ctx.server, None, None, admin=is_admin(ctx)):
            raise StewardError("No activities are setup for you to log.")
        
        player = await Player.get_or_create(self.bot.db, member)
        
        if not player.active_characters:
            raise CharacterNotFound(player)

        ui = CreateLogView(ctx.author, self.bot, player, ctx.server, is_admin(ctx))
        await ctx.send(view=ui, allowed_mentions=discord.AllowedMentions(users=False, roles=False))
        await ctx.delete()

    @commands.slash_command(
        name="info",
        description="Displays information for a player"
        )
    async def player_info(self,
                          ctx: "StewardApplicationContext",
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
        await ctx.send(view=ui, allowed_mentions=discord.AllowedMentions(users=False, roles=False))
        await ctx.delete()

    @commands.slash_command(
        name="submit",
        description="Make a request"
    )
    async def staff_request(
        self,
        ctx: "StewardApplicationContext",
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
        await ctx.send(view=ui, allowed_mentions=discord.AllowedMentions(users=False, roles=False))
        await ctx.delete()

    @commands.slash_command(
        name="apply",
        description="Apply for something or fill out a form"
    )
    async def application(
        self,
        ctx: "StewardApplicationContext",
        application: discord.Option(
            str,
            description="What are you applying for?",
            autocomplete=form_autocomplete
        )
    ):
        from Steward.models.views.forms import FormView
        from Steward.models.modals import get_character_select_modal
        
        template = await FormTemplate.fetch(self.bot.db, ctx.server.id, application)
        
        if not template:
            raise StewardError(f"Application template '{application}' not found")
        
        # Get character if template requires it - show modal popup
        char_obj = None
        if template.character_specific:
            if not ctx.player.active_characters:
                raise StewardError("You don't have any active characters. Please create a character first.")
            
            character = await get_character_select_modal(
                ctx,
                ctx.player.active_characters,
                title=f"Select Character for {template.name}"
            )
            
            if not character:
                raise CharacterNotFound(ctx.player)
        
        # Check for existing draft application
        existing_app = await Application.fetch_draft(
            self.bot.db,
            ctx.guild.id,
            ctx.author.id,
            template.name,
            char_obj.id if char_obj else None
        )

        if existing_app:
            cont = await confirm_view(
                ctx,
                "I found an existing application. Do you wish to continue filling it out?"
            )

            if cont is False:
                discard = await confirm_view(
                    ctx,
                    "Do you wish to discard the old draft?"
                )

                if discard:
                    await existing_app.delete()
                    existing_app = None
                else:
                    await ctx.respond("Application cancelled", ephemeral=True)
                    return
            elif cont is None:
                await ctx.respond("Application confirmation timed out", ephemeral=True)
                return
        
        if existing_app:
            # Load template and relationships for existing app
            existing_app.template = template
            existing_app.player = ctx.player
            existing_app.character = char_obj
            
        # Create and send the form view (with existing app if found)
        form_view = FormView(self.bot, ctx, template, character=char_obj, application=existing_app)
        await form_view.send()
        

    @commands.slash_command(
        name="edit_application",
        description="Edit a submitted application"
    )
    async def edit_application(
        self,
        ctx: "StewardApplicationContext"
    ):
        from Steward.models.views.forms import FormView
        from Steward.models.modals import get_character_select_modal

        if not isinstance(ctx.channel, discord.Thread):
            raise StewardError("This command must be run inside an application thread")

        thread_message_id = ctx.channel.id
        application_obj = await Application.fetch_by_message_id(
            self.bot.db,
            ctx.guild.id,
            thread_message_id
        )

        if not application_obj:
            raise StewardError("Application not found for this thread")

        if application_obj.player_id != ctx.author.id:
            raise StewardError("You don't own this application")

        template = await FormTemplate.fetch(self.bot.db, ctx.server.id, application_obj.template_name)
        if not template:
            raise StewardError("Application template not found")

        character = None
        if application_obj.character_id:
            character = await Character.fetch(self.bot.db, application_obj.character_id)
            if not character or character.player_id != ctx.author.id:
                raise StewardError("Character not found for this application")

        application_obj.template = template
        application_obj.player = ctx.player
        application_obj.character = character

        application_obj.status = "draft"

        form_view = FormView(self.bot, ctx, template, character=character, application=application_obj)
        await form_view.send()
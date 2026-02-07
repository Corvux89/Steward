import traceback
from typing import Union
import discord
import logging
from discord.ext import commands
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from timeit import default_timer as timer

from Steward.models import metadata

from Steward.models.embeds import ErrorEmbed
from Steward.models.objects.exceptions import StewardCommandError, StewardError
from Steward.utils.discordUtils import try_delete
from constants import DB_URL, ERROR_CHANNEL 

# Important for metadata initiation
from Steward.models.objects.npc import NPC
from Steward.models.objects.activityPoints import ActivityPoints
from Steward.models.objects.character import Character
from Steward.models.objects.log import StewardLog
from Steward.models.objects.levels import Levels
from Steward.models.objects.servers import Server
from Steward.models.objects.player import Player
from Steward.models.objects.activity import Activity
from Steward.models.objects.rules import StewardRule
from Steward.models.objects.request import Request
from Steward.models.objects.form import FormTemplate, Application

log = logging.getLogger(__name__)

class StewardContext(commands.Context):
    bot: "StewardBot"
    player: "Player"
    server: "Server"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.player = None
        self.server = None

    def __repr__(self):
        return f"<{self.__class__.__name__} author={self.author.id:!r} channel={self.channel.name:!r}"

class StewardApplicationContext(discord.ApplicationContext):
    bot: "StewardBot"
    player: "Player"
    server: "Server"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.player = None
        self.server = None

    def __repr__(self):
        return f"<{self.__class__.__name__} author={self.author.id:!r} channel={self.channel.name:!r}"
    
class StewardBot(commands.Bot):
    db: AsyncEngine

    def __init__(self, **options):
        super(StewardBot, self).__init__(**options)
        # Compendium

        self.check(self.bot_check)
        self.before_invoke(self.before_invoke_setup)

    async def on_ready(self):
        db_start = timer()
        try:
            log.info("Connecting to database...")
            self.db = create_async_engine(DB_URL)

            async with self.db.begin() as conn:
                await conn.run_sync(metadata.create_all)

            db_end = timer()
            log.info(f"Time to create db engine: {db_end - db_start:.2f}")
            self.dispatch("db_connected")

            log.info(f"Logged in as {self.user} (ID: {self.user.id})")
            log.info("------")
        except Exception:
            log.exception("Failed during on_ready database setup")
            raise

    async def close(self):
        log.info("Cleaning up and shutting down")
        if hasattr(self, "db"):
            await self.db.dispose()

        await super().close()

    async def on_error(self, event_method, *args, **kwargs):
        exception = kwargs.get("exception")
        if exception is None:
            exception = traceback.format_exc()
        log.error(f"Unhandled error in event '{event_method}': {exception}")

    async def on_command_error(self, context, exception):
        await self.error_handling(context, exception)

    async def on_application_command_error(self, context, exception):
        await self.error_handling(context, exception)        

    async def bot_check(self, ctx: Union[discord.ApplicationContext,commands.Context]):
        if (
            hasattr(self, "db")
            and self.db
        ):
            return True
        
        if isinstance(ctx, commands.Context):
            raise StewardCommandError(f"Try again in a few seconds. I'm not fully ready yet.")
        raise StewardError(f"Try again in a few seconds. I'm not fully ready yet.")
    
    async def before_invoke_setup(self, ctx: Union[discord.ApplicationContext, commands.Context]):
        if not hasattr(self, "db") or not self.db:
            raise StewardCommandError(f"Try again in a few seconds. I'm not fully ready yet.")

        ctx: StewardContext = ctx
        
        ctx.server = await Server.get_or_create(self.db, ctx.guild)
        ctx.player = await Player.get_or_create(self.db, ctx.author)

        # Statistics
        await ctx.player.update_command_count(str(ctx.command))


        params = "".join(
            [
                f" [{p['name']}: {p['value']}]"
                for p in (
                    ctx.selected_options
                    if hasattr(ctx, "selected_options") and ctx.selected_options
                    else []
                )
            ]
        )

        try:
            log.info(
                f"cmd: chan {ctx.channel} [{ctx.channel.id}], serv: {f'{ctx.server.name} [{ctx.server.id}]' if ctx.server.id else 'DM'}, "
                f"auth: {ctx.author} [{ctx.author.id}]: {ctx.command}  {params}"
            )
        except AttributeError as e:
            log.info(
                f"Command in DM with {ctx.author} [{ctx.author.id}]: {ctx.command} {params}"
            )

    async def error_handling(
        self, ctx: discord.ApplicationContext | commands.Context, error
    ):
        """
        Handles errors that occur during the execution of application commands.
        Parameters:
        ctx (discord.ApplicationContext): The context in which the command was invoked.
        error (Exception): The error that was raised during command execution.
        Returns:
        None
        This function performs the following actions:
        - If the command has a custom error handler (`on_error`), it returns immediately.
        - If the error is a `CheckFailure`, it responds with a message indicating insufficient permissions.
        - If the error is a `StewardError`, it responds with an embedded error message.
        - Logs detailed error information to a specified error channel or to the log if the error channel is not available.
        - Responds with appropriate messages for specific conditions such as bot not being fully initialized or command not supported in direct messages.
        """
        # Cleanup
        try:
            await ctx.defer()
            await ctx.delete()
        except:
            pass

        if isinstance(error, commands.CommandNotFound) and isinstance(
            ctx, commands.Context
        ):
            return await ctx.send(
                embed=ErrorEmbed(f"No npc with the key `{ctx.invoked_with}` found.")
            )

        elif (
            hasattr(ctx.command, "on_error")
            or isinstance(error, (commands.CommandNotFound))
            or "Unknown interaction" in str(error)
        ):
            return

        elif isinstance(
            error,
            (StewardError, discord.CheckFailure, StewardCommandError, commands.CheckFailure),
        ):
            if isinstance(ctx, (discord.Interaction, discord.ApplicationContext)):
                if ctx.response.is_done():
                    return await ctx.followup.send(embed=ErrorEmbed(error), ephemeral=True)
                else:
                    return await ctx.response.send_message(embed=ErrorEmbed(error), ephemeral=True)
            else:
                return await ctx.send(embed=ErrorEmbed(error))

        if hasattr(ctx, "bot") and hasattr(ctx.bot, "db"):
            params = (
                "".join(
                    [
                        f" [{p['name']}: {p['value']}]"
                        for p in (ctx.selected_options or [])
                    ]
                )
                if hasattr(ctx, "selected_options") and ctx.selected_options
                else ""
            )

            out_str = (
                f"Error in command: cmd: chan {ctx.channel} [{ctx.channel.id}], {f'serv: {ctx.guild} [{ctx.guild.id}]' if ctx.guild else ''} auth: {ctx.author} [{ctx.author.id}]: {ctx.command} {params}\n```"
                f"{''.join(traceback.format_exception(type(error), error, error.__traceback__))}"
                f"```"
            )

            if ERROR_CHANNEL:
                try:
                    await ctx.bot.get_channel(int(ERROR_CHANNEL)).send(out_str)
                except:
                    log.error(out_str)
            else:
                log.error(out_str)

        try:
            await ctx.send(
                embed=ErrorEmbed(f"Something went wrong. Let us know if it keeps up!")
            )
        except:
            log.warning("Unable to respond")


        
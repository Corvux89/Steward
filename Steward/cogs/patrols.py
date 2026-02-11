from datetime import datetime, timezone
import logging
import discord
from discord.ext import commands

from Steward.bot import StewardBot, StewardApplicationContext
from Steward.models.modals import get_value_modal
from Steward.models.objects.enum import PatrolOutcome, RuleTrigger
from Steward.models.objects.exceptions import CharacterNotFound, StewardError
from Steward.models.objects.patrol import Patrol
from Steward.models.views.patrol import PatrolView
from Steward.utils.autocompleteUtils import patrol_outcome_autocomplete
from Steward.utils.discordUtils import is_admin
from constants import CHANNEL_BREAK

log = logging.getLogger(__name__)


def setup(bot: StewardBot):
    bot.add_cog(PatrolCog(bot))


class PatrolCog(commands.Cog):
    bot: StewardBot

    def __init__(self, bot):
        self.bot = bot
        log.info(f"Cog '{self.__cog_name__}' loaded")

    patrol_commands = discord.SlashCommandGroup(
        "patrol",
        "Patrol commands",
        contexts=[discord.InteractionContextType.guild]
    )

    @commands.Cog.listener()
    async def on_db_connected(self):
        patrols = await Patrol.fetch_all(self.bot)

        for patrol in patrols:
            await patrol.refresh_view(self.bot)

    @commands.Cog.listener()
    async def on_channel_delete(self, channel):
        if not hasattr(self.bot, "db"):
            return

        if (patrol := await Patrol.fetch(self.bot, channel)):
            patrol.end_ts = datetime.now(timezone.utc)
            await patrol.upsert()

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not hasattr(self.bot, "db"):
            return

        if (patrol := await Patrol.fetch(self.bot, message.channel, message.id)):
            patrol.end_ts = datetime.now(timezone.utc)
            await patrol.upsert()

    @patrol_commands.command(
        name="claim",
        description="Claim a channel for a patrol"
    )
    async def patrol_claim(self, ctx: "StewardApplicationContext"):
        if not ctx.player.active_characters:
            raise CharacterNotFound(ctx.player)
        
        if patrol := await Patrol.fetch(self.bot, ctx.channel):
            raise StewardError("Patrol already active for this channel")

        patrol = Patrol(self.bot.db, ctx.channel, ctx.player)
        view = PatrolView(self.bot, patrol)

        message = await ctx.channel.send(view=view, allowed_mentions=discord.AllowedMentions(users=False, roles=False))
        patrol.pinned_message_id = message.id

        await patrol.upsert()

        await ctx.respond("Patrol open for recruitment!", ephemeral=True)

    @patrol_commands.command(
        name="notes",
        description="Edit Notes for a patrol"
    )
    async def patrol_notes(self, ctx: "StewardApplicationContext"):
        patrol = await Patrol.fetch(self.bot, ctx.channel)

        if not patrol:
            raise StewardError("No patrol active in this channel")
        
        if not(ctx.player.id == patrol.host.id or is_admin(ctx)):
            raise StewardError("You are not in charge of this patrol")
        
        patrol.notes = await get_value_modal(
            ctx,
            "Patrol Notes",
            patrol.notes,
            "Patrol Notes",
            max_length=800,
            style="long"
        )

        await patrol.upsert()
        await patrol.refresh_view(self.bot)

    @patrol_commands.command(
        name="complete",
        description="Finishes and a Patrol"
    )
    async def patrol_complete(
        self, 
        ctx: "StewardApplicationContext", 
        outcome: discord.Option(
            str,
            description="Patrol outcome",
            autocomplete=patrol_outcome_autocomplete
        )
    ):
        patrol = await Patrol.fetch(self.bot, ctx.channel)

        if not patrol:
            raise StewardError("No patrol active in this channel")
        
        if not(ctx.player.id == patrol.host.id or is_admin(ctx)):
            raise StewardError("You are not in charge of this patrol")
        
        if not (outcome := PatrolOutcome(outcome)):
            raise StewardError("Invalid Difficulty")
        
        patrol.outcome = outcome.name

        try:
            message = await patrol.channel.fetch_message(patrol.pinned_message_id)
            await message.delete()
        except:
            pass

        await ctx.channel.send(CHANNEL_BREAK)

        patrol.end_ts = datetime.now(timezone.utc)
        await patrol.upsert()
        self.bot.dispatch(RuleTrigger.patrol_complete.name, patrol)





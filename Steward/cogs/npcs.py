import logging
from discord.ext import commands
from timeit import default_timer as timer

from Steward.bot import StewardBot
from Steward.models.objects.npc import NPC
from Steward.models.objects.enum import WebhookType
from Steward.models.objects.webhook import StewardWebhook

log = logging.getLogger(__name__)


def setup(bot: StewardBot):
    bot.add_cog(NPCCog(bot))


class NPCCog(commands.Cog):
    bot: StewardBot

    def __init__(self, bot):
        self.bot = bot
        log.info(f"Cog '{self.__cog_name__}' loaded")

    @commands.Cog.listener()
    async def on_db_connected(self):
        start = timer()
        npcs = await NPC.get_all(self.bot.db)

        for npc in npcs:
            await npc.register_command(self.bot)
        end = timer()
        log.info(f"NPC: NPC's loaded in [ {end-start:.2f} ]s")

    def create_npc_command(self, npc: NPC):
        async def npc_command(ctx):
            if ctx.invoked_with == "say":
                return

            adventure = None
            # if npc.adventure_id:
            #     try:
            #         adventure = Adventure.fetch_from_ctx(
            #             ctx, adventure_id=npc.adventure_id
            #         )
            #     except AdventureNotFound:
            #         raise G0T0CommandError(
            #             "This npc can only be used in it's designated Adventure"
            #         )

            type = WebhookType.adventure if npc.adventure_id else WebhookType.npc
            await StewardWebhook(ctx, type=type, adventure=adventure).send()

        return npc_command

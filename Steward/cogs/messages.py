import logging
import discord
from discord.ext import commands


from Steward.bot import StewardBot, StewardContext
from Steward.models.modals import get_value_modal
from Steward.models.modals.messages import SayEditModal
from Steward.models.objects.enum import WebhookType
from Steward.models.objects.exceptions import StewardError
from Steward.models.objects.webhook import StewardWebhook
from Steward.models.objects.request import Request
from Steward.models.views import confirm_view
from Steward.utils.discordUtils import is_staff

log = logging.getLogger(__name__)


def setup(bot: StewardBot):
    bot.add_cog(MessageCog(bot))


class MessageCog(commands.Cog):
    bot: StewardBot

    def __init__(self, bot):
        self.bot = bot
        log.info(f"Cog '{self.__cog_name__}' loaded")

    @commands.message_command(name="Edit")
    async def message_edit(self, ctx: StewardContext, message: discord.Message):
        # Character Message
        if (
            (webhook := StewardWebhook(ctx, message=message))
            and await webhook.is_valid_message()
        ):
            modal = SayEditModal(ctx.bot, webhook)
            return await ctx.send_modal(modal)
        
        # NPC Message
        elif (
            (webhook := StewardWebhook(ctx, type=WebhookType.npc, message=message))
            and await webhook.is_valid_message()
            and await webhook.user_is_authorized_for_npc()
        ):
            modal = SayEditModal(ctx.bot, webhook)
            return await ctx.send_modal(modal)
        
        else:
            raise StewardError("This message cannot be edited")
        
    @commands.message_command(name="Delete")
    async def message_delete(self, ctx: StewardContext, message: discord.Message):
         # Character Message
        if (
            (webhook := StewardWebhook(ctx, message=message))
            and await webhook.is_valid_message()
        ):
            await webhook.delete()
        
        # NPC Message
        elif (
            (webhook := StewardWebhook(ctx, type=WebhookType.npc, message=message))
            and await webhook.is_valid_message()
            and await webhook.user_is_authorized_for_npc()
        ):
            await webhook.delete()
        
        # Request
        elif (
            (request := await Request.fetch(self.bot, message.id))
            and await is_staff(ctx) == True
        ):
            if await confirm_view(ctx, "Are you sure you want to cancel this request?") == True:
                await request.delete()

        else:
            raise StewardError("This message cannot be deleted")
        
        await ctx.delete()

    @commands.message_command(name="Approve")
    @commands.check(is_staff)
    async def message_approve(self, ctx: StewardContext, message: discord.Message):
        # Request
        if (
            request := await Request.fetch(self.bot, message.id)
        ):
            act_list = [a.name for a in ctx.server.activities]
            act = await get_value_modal(
                ctx,
                "Activity",
                "",
                "Select an activity",
                items=act_list
            )

            activity = ctx.server.get_activity(act)

            if activity:
                await request.approve(self.bot, activity, ctx.author)
            else:
                raise StewardError("No activity specified")

        else:
            raise StewardError("What are you approving?")

            


            

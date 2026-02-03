import discord

from ..models.objects.servers import Server
from ..models.objects.player import Player
from ..models.objects.form import FormTemplate
    
async def activity_autocomplete(ctx: discord.AutocompleteContext):
        server = await Server.get_or_create(ctx.bot.db, ctx.interaction.guild)
        
        return [
            a.name for a in server.activities
        ] or []

async def character_autocomplete(ctx: discord.AutocompleteContext):
        member = ctx.interaction.guild.get_member(ctx.interaction.user.id)
        player = await Player.get_or_create(ctx.bot.db, member)

        return [
                c.name for c in player.active_characters
        ] or []

async def form_autocomplete(ctx: discord.AutocompleteContext):
        templates =  await FormTemplate.fetch_all(ctx.bot.db, ctx.interaction.guild.id)

        return [
                t.name for t in templates
        ] or []
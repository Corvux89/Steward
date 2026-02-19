import discord

from Steward.models.objects.enum import PatrolOutcome

from ..models.objects.servers import Server
from ..models.objects.player import Player
from ..models.objects.form import FormTemplate
from ..models.objects.activity import Activity
from ..models.objects.auctionHouse import AuctionHouse
    
async def activity_autocomplete(ctx: discord.AutocompleteContext):
    """Lightweight autocomplete for activities - loads only activities without full server data"""
    try:
        # Load activities directly without full server initialization
        activities = await Activity.fetch_by_guild(ctx.bot.db, ctx.interaction.guild.id)
        
        # Filter based on user input for faster response
        user_input = ctx.value.lower() if ctx.value else ""
        filtered = [a.name for a in activities if user_input in a.name.lower()]
        
        return filtered[:25] or []
    except Exception:
        return []

async def character_autocomplete(ctx: discord.AutocompleteContext):
    """Lightweight autocomplete for characters"""
    try:
        member = ctx.interaction.guild.get_member(ctx.interaction.user.id)
        # Use lightweight player fetch if available, otherwise fall back to get_or_create
        player = await Player.get_or_create(ctx.bot.db, member)

        # Filter based on user input for faster response
        user_input = ctx.value.lower() if ctx.value else ""
        characters = [c.name for c in player.active_characters if user_input in c.name.lower()]
        
        return characters[:25] or []
    except Exception:
        return []

async def form_autocomplete(ctx: discord.AutocompleteContext):
    """Lightweight autocomplete for form templates"""
    try:
        templates = await FormTemplate.fetch_all(ctx.bot.db, ctx.interaction.guild.id)

        # Filter based on user input for faster response
        user_input = ctx.value.lower() if ctx.value else ""
        forms = [t.name for t in templates if user_input in t.name.lower()]
        
        return forms[:25] or []
    except Exception:
        return []

async def patrol_outcome_autocomplete(ctx: discord.AutocompleteContext):
    """Autocomplete for patrol outcomes - no DB query needed"""
    try:
        # Filter based on user input for faster response
        user_input = ctx.value.lower() if ctx.value else ""
        outcomes = [c.value for c in PatrolOutcome if user_input in c.value.lower()]
        
        return outcomes[:25] or []
    except Exception:
        return []

async def auction_house_autocomplete(ctx: discord.AutocompleteContext):
    """Autocomplete for auction house names in the current guild"""
    try:
        houses = await AuctionHouse.fetch_all(ctx.bot, load_related=False)
        user_input = ctx.value.lower() if ctx.value else ""

        names = [
            house.name
            for house in houses
            if house.guild_id == ctx.interaction.guild.id
            and house.name
            and user_input in house.name.lower()
        ]

        return names[:25] or []
    except Exception:
        return []
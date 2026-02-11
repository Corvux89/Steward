from typing import TYPE_CHECKING, Union
import sqlalchemy as sa
import uuid

from marshmallow import Schema, fields, post_load
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncEngine

from Steward.models.objects.enum import LogEvent, MarketType

from ...models import metadata
from ...utils.dbUtils import execute_query

if TYPE_CHECKING:
    from .player import Player
    from ...bot import StewardApplicationContext, StewardBot

class Item:
    def __init__(self, db: AsyncEngine, **kwargs):
        self.market_id = kwargs.get("market_id")
        self.name = kwargs.get("name")
        self.description = kwargs.get("description")
        self.category = kwargs.get("category")
        self.max_qty = kwargs.get("max_qty")

    item_table = sa.Table(
        "ref_items",
        metadata,
        sa.Column("market_id", sa.UUID, sa.ForeignKey("ref_markets.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullabl=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("max_qty", sa.Integer, nullable=True),
        sa.PrimaryKeyConstraint("market_id", "name")
    )

class InventoryItem:
    def __init__(self, db: AsyncEngine, **kwargs):
        pass

class Shelf:
    def __init__(self, db: AsyncEngine, **kwargs):
        pass

class Market:
    def __init__(self, bot: "StewardBot", **kwargs):
        self._bot = bot

        self.id = kwargs.get("id")
        self.guild_id = kwargs.get("guild_id")
        self.channel_id = kwargs.get("channel_id")

        self.role_ids = kwargs.get("role_ids", [])

        self.inventory = kwargs.get("inventory", [])

        self.type: MarketType = kwargs.get("type", MarketType.shop)

        self.auction_length = kwargs.get("auction_length") # Length in hours
        self.reroll_interval = kwargs.get("reroll_interval") # Interval in hours

        # Post Load Items
        self.items: list["Item"] = kwargs.get("items", [])
        self.inventory: list["InventoryItem"] = kwargs.get("inventory", [])
        self.shelves: list["Shelf"] = kwargs.get("shelves", [])

    @property
    def guild(self):
        return self._bot.get_guild(self.guild_id)

    @property
    def channel(self):
        return self.guild.get_channel(self.channel_id)
    
    @property
    def roles(self):
        return [self.guild.get_role(r) for r in self.role_ids if  self.guild.get_role(r)]
    







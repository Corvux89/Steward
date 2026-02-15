from typing import TYPE_CHECKING, Union
import sqlalchemy as sa
import uuid

from marshmallow import Schema, fields, post_load
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncEngine

from Steward.models.objects.enum import LogEvent, MarketType, QueryResultType

from ...models import metadata
from ...utils.dbUtils import execute_query

if TYPE_CHECKING:
    from .player import Player
    from ...bot import StewardApplicationContext, StewardBot

class Item:
    def __init__(self, db: AsyncEngine, **kwargs):
        self._db = db

        self.id = kwargs.get("id")
        self.market_id = kwargs.get("market_id")
        self.name = kwargs.get("name")
        self.description = kwargs.get("description")
        self.category = kwargs.get("category")
        self.cost = kwargs.get("cost", 0)
        self.max_qty = kwargs.get("max_qty")
        self.min_qty = kwargs.get("min_qty")
        self.min_bid = kwargs.get("min_bid")

    item_table = sa.Table(
        "ref_items",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("market_id", sa.UUID, sa.ForeignKey("ref_markets.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullabl=True),
        sa.Column("cost", sa.Float, nullable=False, default=0)
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("max_qty", sa.Integer, nullable=True),
        sa.Column("min_qty", sa.Integer, nullable=True),
        sa.Column("min_bid", sa.Integer, nullable=True),
    )

    class ItemSchema(Schema):
        marked_id = fields.UUID(required=True)
        name = fields.String(required=True)
        description = fields.String(allow_none=True)
        cost = fields.Integer(required=True)
        category = fields.String(allow_none=True)
        max_qty = fields.Integer(allow_none=True)
        min_qty = fields.Integer(allow_none=True)
        min_bid = fields.Integer(allow_none=True)

    async def delete(self):
        query = (
            self.item_table.delete()
            .where(
                sa.and_(
                    self.item_table.c.market_id == self.market_id,
                    self.item_table.c.name == self.name
                )
            )
        )

        await execute_query(self._db, query, QueryResultType.none)

    async def upsert(self):
        update_dict ={
            "name": self.name,
            "description": self.description,
            "cost": self.cost,
            "category": self.category,
            "max_qty": self.max_qty,
            "min_qty": self.min_qty,
            "min_bid": self.min_bid
        }

        insert_dict = {
            "market_id": self.market_id,
            **update_dict
        }

        if hasattr(self, "id") and self.id is not None:
            query = (
                self.item_table.update()
                .values(**update_dict)
                .where(self.item_table.c.id == self.id)
                .returning(self.item_table)
            )
        else:
            query (
                self.item_table.insert()
                .values(**insert_dict)
                .returning(self.item_table)
            )

        result = await execute_query(self._db, query)

        if self.id is None and result:
            self.id = dict(result._mapping)["id"]

        return self

class Shelf:
    def __init__(self, db: AsyncEngine, **kwargs):
        self.id = kwargs.get("id")
        self.market_id = kwargs.get("market_id")
        self.notes = kwargs.get("notes")
        self.max_qty = kwargs.get("max_qty")




class InventoryItem:
    def __init__(self, db: AsyncEngine, **kwargs):
        pass

class Market:
    def __init__(self, bot: "StewardBot", **kwargs):
        self._bot = bot

        self.id = kwargs.get("id")
        self.name = kwargs.get("name")
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
    







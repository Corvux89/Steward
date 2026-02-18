from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional, Union
import sqlalchemy as sa
import uuid

from marshmallow import Schema, fields, post_load
from sqlalchemy.ext.asyncio import AsyncEngine

from Steward.models.objects.enum import QueryResultType, RuleTrigger

from .. import metadata
from ...utils.dbUtils import execute_query

if TYPE_CHECKING:
    from .character import Character
    from .player import Player
    from ...bot import StewardApplicationContext, StewardBot

class Item:
    def __init__(self, db: AsyncEngine, **kwargs):
        self._db = db

        self.id = kwargs.get("id")
        self.house_id = kwargs.get("house_id")
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
        sa.Column("house_id", sa.UUID, sa.ForeignKey("ref_markets.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("cost", sa.Float, nullable=False, default=0),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("max_qty", sa.Integer, nullable=True),
        sa.Column("min_qty", sa.Integer, nullable=True),
        sa.Column("min_bid", sa.Integer, nullable=True),
    )

    class ItemSchema(Schema):
        db: AsyncEngine

        id = fields.UUID(required=False, allow_none=True)
        house_id = fields.UUID(required=True)
        name = fields.String(required=True)
        description = fields.String(allow_none=True)
        cost = fields.Float(required=True)
        category = fields.String(allow_none=True)
        max_qty = fields.Integer(allow_none=True)
        min_qty = fields.Integer(allow_none=True)
        min_bid = fields.Integer(allow_none=True)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db

        @post_load
        def make_item(self, data, **kwargs):
            return Item(self.db, **data)

    async def delete(self):
        if not self.id:
            return

        query = (
            self.item_table.delete()
            .where(
                self.item_table.c.id == self.id
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
            "house_id": self.house_id,
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
            query = (
                self.item_table.insert()
                .values(**insert_dict)
                .returning(self.item_table)
            )

        result = await execute_query(self._db, query)

        if not result:
            return self

        return Item.ItemSchema(self._db).load(dict(result._mapping))

    @staticmethod
    async def fetch(db: AsyncEngine, item_id: Union[uuid.UUID, str]) -> Optional["Item"]:
        if isinstance(item_id, str):
            item_id = uuid.UUID(item_id)

        query = (
            Item.item_table.select()
            .where(Item.item_table.c.id == item_id)
        )

        row = await execute_query(db, query)

        if not row:
            return None

        return Item.ItemSchema(db).load(dict(row._mapping))

    @staticmethod
    async def fetch_by_house(db: AsyncEngine, house_id: Union[uuid.UUID, str]) -> list["Item"]:
        if isinstance(house_id, str):
            house_id = uuid.UUID(house_id)

        query = (
            Item.item_table.select()
            .where(Item.item_table.c.house_id == house_id)
            .order_by(Item.item_table.c.name)
        )

        rows = await execute_query(db, query, QueryResultType.multiple)

        if not rows:
            return []

        return [Item.ItemSchema(db).load(dict(row._mapping)) for row in rows]

class Shelf:
    def __init__(self, db: AsyncEngine, **kwargs):
        self._db = db

        self.id = kwargs.get("id")
        self.priority = kwargs.get("priority", 0)
        self.house_id = kwargs.get("house_id")
        self.notes = kwargs.get("notes")
        self.max_qty = kwargs.get("max_qty", 1)

        self.items: list["StockItem"] = kwargs.get("items", [])

    shelf_table = sa.Table(
        "ref_shelves",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("house_id", sa.UUID, sa.ForeignKey("ref_auction_houses.id"), nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, default=0),
        sa.Column("notes", sa.String, nullable=True),
        sa.Column("max_qty", sa.Integer, nullable=False, default=1)
    )

    class ShelfSchema(Schema):
        db: AsyncEngine

        id = fields.UUID(required=False, allow_none=True)
        house_id = fields.UUID(required=True)
        priority = fields.Integer(required=True)
        notes = fields.String(allow_none=True)
        max_qty = fields.Integer(required=True)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db

        @post_load
        def make_shelf(self, data, **kwargs):
            return Shelf(self.db, **data)

    async def delete(self):
        if not self.id:
            return

        query = (
            self.shelf_table.delete()
            .where(
                self.shelf_table.c.id == self.id
            )
        )

        await execute_query(self._db, query, QueryResultType.none)

    async def upsert(self):
        update_dict = {
            "priority": self.priority,
            "notes": self.notes,
            "max_qty": self.max_qty
        }

        insert_dict = {
            "house_id": self.house_id,
            **update_dict
        }

        if hasattr(self, "id") and self.id is not None:
            query = (
                self.shelf_table.update()
                .values(**update_dict)
                .where(self.shelf_table.c.id == self.id)
                .returning(self.shelf_table)
            )
        else:
            query = (
                self.shelf_table.insert()
                .values(**insert_dict)
                .returning(self.shelf_table)
            )

        result = await execute_query(self._db, query)

        if not result:
            return self

        return Shelf.ShelfSchema(self._db).load(dict(result._mapping))

    @staticmethod
    async def fetch(db: AsyncEngine, shelf_id: Union[uuid.UUID, str]) -> Optional["Shelf"]:
        if isinstance(shelf_id, str):
            shelf_id = uuid.UUID(shelf_id)

        query = (
            Shelf.shelf_table.select()
            .where(Shelf.shelf_table.c.id == shelf_id)
        )

        row = await execute_query(db, query)

        if not row:
            return None

        return Shelf.ShelfSchema(db).load(dict(row._mapping))

    @staticmethod
    async def fetch_by_market(db: AsyncEngine, house_id: Union[uuid.UUID, str]) -> list["Shelf"]:
        if isinstance(house_id, str):
            house_id = uuid.UUID(house_id)

        query = (
            Shelf.shelf_table.select()
            .where(Shelf.shelf_table.c.house_id == house_id)
            .order_by(Shelf.shelf_table.c.priority, Shelf.shelf_table.c.id)
        )

        rows = await execute_query(db, query, QueryResultType.multiple)

        if not rows:
            return []

        return [Shelf.ShelfSchema(db).load(dict(row._mapping)) for row in rows]

    async def load_items(self) -> list["StockItem"]:
        if not self.id:
            self.items = []
            return self.items

        items = [inv for inv in (await StockItem.fetch_by_market(self._db, self.house_id, load_bids=False)) if inv.shelf_id == self.id]
        self.items = items
        return items

class StockItem:
    def __init__(self, db: AsyncEngine, **kwargs):
        self._db = db

        self.id = kwargs.get("id")
        self.item_id = kwargs.get("item_id")
        self.shelf_id = kwargs.get("shelf_id")
        self.bids: dict["Character", int] = kwargs.get("bids", {})
        self.auction_start = kwargs.get("auction_start", datetime.now(timezone.utc))

        self.item: Optional["Item"] = kwargs.get("item")
        self.shelf: Optional["Shelf"] = kwargs.get("shelf")

    inventory_item_table = sa.Table(
        "ref_stock_items",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("item_id", sa.UUID, sa.ForeignKey("ref_items.id"), nullable=False),
        sa.Column("shelf_id", sa.UUID, sa.ForeignKey("ref_shelves.id"), nullable=False),
        sa.Column("auction_start", sa.TIMESTAMP(timezone=True), nullable=False)
    )

    class InventoryItemSchema(Schema):
        db: AsyncEngine

        id = fields.UUID(required=False, allow_none=True)
        item_id = fields.UUID(required=True)
        shelf_id = fields.UUID(required=True)
        auction_start = fields.DateTime(required=False, allow_none=True)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db

        @post_load
        def make_inventory_item(self, data, **kwargs) -> "StockItem":
            return StockItem(self.db, **data)

    item_bids = sa.Table(
        "ref_bids",
        metadata,
        sa.Column("inventory_id", sa.UUID, sa.ForeignKey("ref_stock_items.id"), primary_key=True),
        sa.Column("character_id", sa.UUID, sa.ForeignKey("characters.id"), primary_key=True),
        sa.Column("bid", sa.Integer, nullable=False)

    )

    class ItemBid(Schema):
        inventory_id = fields.UUID(required=True)
        character_id = fields.UUID(required=True)
        bid = fields.Integer(required=True)

        @post_load
        def make_bid(self, data, **kwargs) -> dict:
            return data

    async def delete(self):
        if not self.id:
            return

        bid_query = (
            self.item_bids.delete()
            .where(self.item_bids.c.inventory_id == self.id)
        )
        await execute_query(self._db, bid_query, QueryResultType.none)

        inv_query = (
            self.inventory_item_table.delete()
            .where(self.inventory_item_table.c.id == self.id)
        )
        await execute_query(self._db, inv_query, QueryResultType.none)

    async def upsert(self) -> "StockItem":
        update_dict = {
            "item_id": self.item_id,
            "shelf_id": self.shelf_id,
            "auction_start": self.auction_start,
        }

        if self.id:
            query = (
                self.inventory_item_table.update()
                .where(self.inventory_item_table.c.id == self.id)
                .values(**update_dict)
                .returning(self.inventory_item_table)
            )
        else:
            query = (
                self.inventory_item_table.insert()
                .values(**update_dict)
                .returning(self.inventory_item_table)
            )

        row = await execute_query(self._db, query)

        if not row:
            return self

        inv_item = StockItem.InventoryItemSchema(self._db).load(dict(row._mapping))

        if self.bids is not None:
            inv_item.bids = self.bids
            await inv_item.upsert_bids(self.bids)

        return inv_item

    async def upsert_bids(self, bids: dict[Union["Character", uuid.UUID, str], int]):
        from .character import Character

        if not self.id:
            return

        delete_query = (
            self.item_bids.delete()
            .where(self.item_bids.c.inventory_id == self.id)
        )
        await execute_query(self._db, delete_query, QueryResultType.none)

        if not bids:
            self.bids = {}
            return

        normalized = []
        hydrated: dict["Character", int] = {}
        for character_or_id, bid in bids.items():
            if hasattr(character_or_id, "id"):
                character = character_or_id
                character_id = character.id
            else:
                character_id = uuid.UUID(character_or_id) if isinstance(character_or_id, str) else character_or_id
                character = await Character.fetch(self._db, character_id, active_only=False)

            if not character:
                continue

            normalized.append(
                {
                    "inventory_id": self.id,
                    "character_id": character.id,
                    "bid": int(bid),
                }
            )
            hydrated[character] = int(bid)

        if normalized:
            insert_query = self.item_bids.insert().values(normalized)
            await execute_query(self._db, insert_query, QueryResultType.none)

        self.bids = hydrated

    async def load_bids(self) -> dict["Character", int]:
        from .character import Character

        if not self.id:
            self.bids = {}
            return self.bids

        query = (
            self.item_bids.select()
            .where(self.item_bids.c.inventory_id == self.id)
            .order_by(self.item_bids.c.bid.desc())
        )

        rows = await execute_query(self._db, query, QueryResultType.multiple)

        if not rows:
            self.bids = {}
            return self.bids

        bids: dict["Character", int] = {}
        for row in rows:
            data = self.ItemBid().load(dict(row._mapping))
            character = await Character.fetch(self._db, data["character_id"], active_only=False)
            if character:
                bids[character] = data["bid"]

        self.bids = bids
        return bids

    @staticmethod
    async def fetch(db: AsyncEngine, inventory_id: Union[uuid.UUID, str], load_bids: bool = True) -> Optional["StockItem"]:
        if isinstance(inventory_id, str):
            inventory_id = uuid.UUID(inventory_id)

        query = (
            StockItem.inventory_item_table.select()
            .where(StockItem.inventory_item_table.c.id == inventory_id)
        )

        row = await execute_query(db, query)

        if not row:
            return None

        item = StockItem.InventoryItemSchema(db).load(dict(row._mapping))

        if load_bids:
            await item.load_bids()

        return item

    @staticmethod
    async def fetch_by_market(db: AsyncEngine, house_id: Union[uuid.UUID, str], load_bids: bool = True) -> list["StockItem"]:
        if isinstance(house_id, str):
            house_id = uuid.UUID(house_id)

        query = (
            StockItem.inventory_item_table
            .select()
            .join(Shelf.shelf_table, StockItem.inventory_item_table.c.shelf_id == Shelf.shelf_table.c.id)
            .where(Shelf.shelf_table.c.house_id == house_id)
            .order_by(Shelf.shelf_table.c.priority, StockItem.inventory_item_table.c.auction_start)
        )

        rows = await execute_query(db, query, QueryResultType.multiple)

        if not rows:
            return []

        items = [StockItem.InventoryItemSchema(db).load(dict(row._mapping)) for row in rows]

        if load_bids:
            for item in items:
                await item.load_bids()

        return items


class AuctionHouse:
    def __init__(self, bot: "StewardBot", **kwargs):
        self._bot = bot

        self.id = kwargs.get("id")
        self.name = kwargs.get("name")
        self.guild_id = kwargs.get("guild_id")
        self.channel_id = kwargs.get("channel_id")
        self.message_id = kwargs.get("message_id")
        self.min_bid_percent = kwargs.get('min_bid_percent', 100)
        self.auction_length = kwargs.get("auction_length") # Length in hours
        self.reroll_interval = kwargs.get("reroll_interval") # Interval in hours

        # Post Load Items
        self.items: list["Item"] = kwargs.get("items", [])
        self.inventory: list["StockItem"] = kwargs.get("inventory", [])
        self.shelves: list["Shelf"] = kwargs.get("shelves", [])

    market_table = sa.Table(
        "ref_auction_houses",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers.id"), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("min_bid_percent", sa.DECIMAL(), nullable=True),
        sa.Column("auction_length", sa.DECIMAL(), nullable=True),
        sa.Column("reroll_interval", sa.DECIMAL(), nullable=True)
    )

    @property
    def guild(self):
        return self._bot.get_guild(self.guild_id)

    @property
    def channel(self):
        guild = self.guild
        if not guild:
            return None
        return guild.get_channel(self.channel_id)
    
    class AuctionHouseSchema(Schema):
        bot: "StewardBot"

        id = fields.UUID(required=False, allow_none=True)
        name = fields.String(required=True)
        guild_id = fields.Integer(required=True)
        channel_id = fields.Integer(required=True)
        message_id = fields.Integer(required=True)
        type = fields.String(required=False, allow_none=True)
        min_bid_percent = fields.Float(required=False, allow_none=True)
        auction_length = fields.Float(required=False, allow_none=True)
        reroll_interval = fields.Float(required=False, allow_none=True)

        def __init__(self, bot: "StewardBot", **kwargs):
            super().__init__(**kwargs)
            self.bot = bot

        @post_load
        def make_market(self, data, **kwargs):
            return AuctionHouse(self.bot, **data)

    async def delete(self):
        if not self.id:
            return

        query = (
            self.market_table.delete()
            .where(self.market_table.c.id == self.id)
        )

        await execute_query(self._bot.db, query, QueryResultType.none)

    async def upsert(self) -> "AuctionHouse":
        update_dict = {
            "name": self.name,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "min_bid_percent": self.min_bid_percent,
            "auction_length": self.auction_length,
            "reroll_interval": self.reroll_interval,
        }

        if self.id:
            query = (
                self.market_table.update()
                .where(self.market_table.c.id == self.id)
                .values(**update_dict)
                .returning(self.market_table)
            )
        else:
            query = (
                self.market_table.insert()
                .values(**update_dict)
                .returning(self.market_table)
            )

        row = await execute_query(self._bot.db, query)

        if not row:
            return self

        return self.AuctionHouseSchema(self._bot).load(dict(row._mapping))

    @staticmethod
    async def fetch(bot: "StewardBot", guild_id: int, load_related: bool = True) -> Union["AuctionHouse", None]:
        query = (
            AuctionHouse.market_table.select()
            .where(AuctionHouse.market_table.c.guild_id == guild_id)
            .order_by(AuctionHouse.market_table.c.name)
            .limit(1)
        )

        row = await execute_query(bot.db, query)

        if not row:
            return None

        market = AuctionHouse.AuctionHouseSchema(bot).load(dict(row._mapping))

        if load_related:
            await AuctionHouse._load_related(bot, market)

        return market

    @staticmethod
    async def fetch_by_id(bot: "StewardBot", house_id: Union[uuid.UUID, str], load_related: bool = True) -> Union["AuctionHouse", None]:
        if isinstance(house_id, str):
            house_id = uuid.UUID(house_id)

        query = (
            AuctionHouse.market_table.select()
            .where(AuctionHouse.market_table.c.id == house_id)
        )

        row = await execute_query(bot.db, query)

        if not row:
            return None

        market = AuctionHouse.AuctionHouseSchema(bot).load(dict(row._mapping))

        if load_related:
            await AuctionHouse._load_related(bot, market)

        return market

    @staticmethod
    async def fetch_all(bot: "StewardBot", guild_id: int, load_related: bool = True) -> list["AuctionHouse"]:
        query = (
            AuctionHouse.market_table.select()
            .where(AuctionHouse.market_table.c.guild_id == guild_id)
            .order_by(AuctionHouse.market_table.c.name)
        )

        rows = await execute_query(bot.db, query, QueryResultType.multiple)

        if not rows:
            return []

        markets = [AuctionHouse.AuctionHouseSchema(bot).load(dict(row._mapping)) for row in rows]

        if load_related:
            for market in markets:
                await AuctionHouse._load_related(bot, market)

        return markets

    @staticmethod
    async def _load_related(bot: "StewardBot", market: "AuctionHouse"):
        market.items = await Item.fetch_by_house(bot.db, market.id)
        market.shelves = await Shelf.fetch_by_market(bot.db, market.id)
        market.inventory = await StockItem.fetch_by_market(bot.db, market.id, load_bids=True)

        items_by_id = {item.id: item for item in market.items}
        shelves_by_id = {shelf.id: shelf for shelf in market.shelves}

        for inv_item in market.inventory:
            inv_item.item = items_by_id.get(inv_item.item_id)
            inv_item.shelf = shelves_by_id.get(inv_item.shelf_id)

        # Populate shelf inventory items
        for shelf in market.shelves:
            shelf.items = [inv for inv in market.inventory if inv.shelf_id == shelf.id]

    def minimum_bid(self, item: "Item") -> float:
        if item.min_bid and item.min_bid is not None:
            return item.min_bid
        
        percentage_floor = (item.cost or 0) * ((self.min_bid_percent or 100) / 100)

        return percentage_floor
    
    def next_reroll_at(self):
        if not self.reroll_interval:
            return None

        if not self.inventory:
            return datetime.now(timezone.utc)
        
        earliest = min(inv.auction_start for inv in self.inventory if inv.auction_start)
        if not earliest:
            return datetime.now(timezone.utc)

        return earliest + timedelta(hours=float(self.reroll_interval))
    
    def auction_end_at(self, inventory_item: "StockItem"):
        if not inventory_item.auction_start:
            return None
        
        times = []

        if self.auction_length:
            times.append(inventory_item.auction_start + timedelta(hours=float(self.auction_length)))

        next_reroll = self.next_reroll_at()
        if next_reroll:
            times.append(next_reroll)

        if not times:
            return None
        return min(times)

    async def finalize_item(self, inventory_item: "StockItem", reason: str):
        from Steward.models.objects.log import StewardLog

        # Make sure we're current
        inventory_item = next(
            (inv for inv in self.inventory if inv.id == inventory_item.id),
            None
        )

        if not inventory_item:
            return

        item = next(
            (itm for itm in self.items if itm.id == inventory_item.item_id), 
            None
        )

        if not item:
            await inventory_item.delete()
            return
        
        minimum = self.minimum_bid(item)
        bids = sorted(
            (inventory_item.bids or {}).items(), key=lambda pair: pair[1], reverse=True
        )

        winner = None
        winning_bid = None

        for character, bid in bids:
            if bid < minimum:
                continue

            if character.currency >= bid:
                winner = character
                winning_bid = bid
                break

        if winner and winning_bid is not None:
            self._bot.dispatch(RuleTrigger.auction_complete.name, item, winner, winning_bid, bids, reason)
        await inventory_item.delete()

        #TODO: Refresh view
    
            

        




        
    







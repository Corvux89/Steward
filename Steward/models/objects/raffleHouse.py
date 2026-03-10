from datetime import datetime, timedelta, timezone
import random
from typing import TYPE_CHECKING, Optional, Union
import sqlalchemy as sa
import uuid

from marshmallow import Schema, fields, post_load
from sqlalchemy.ext.asyncio import AsyncEngine

from Steward.models.objects.enum import LogEvent, QueryResultType, RuleTrigger

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
        sa.Column("house_id", sa.UUID, sa.ForeignKey("ref_auction_houses.id"), nullable=False),
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
    async def fetch_by_house(db: AsyncEngine, house_id: Union[uuid.UUID, str]) -> list["Shelf"]:
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

        items = [inv for inv in (await StockItem.fetch_by_house(self._db, self.house_id, load_tickets=False)) if inv.shelf_id == self.id]
        self.items = items
        return items

class StockItem:
    def __init__(self, db: AsyncEngine, **kwargs):
        self._db = db

        self.id = kwargs.get("id")
        self.item_id = kwargs.get("item_id")
        self.shelf_id = kwargs.get("shelf_id")
        self.tickets: dict["Character", int] = kwargs.get("tickets", kwargs.get("bids", {}))
        self.auction_start = kwargs.get("auction_start")

        self.item: Optional["Item"] = kwargs.get("item")
        self.shelf: Optional["Shelf"] = kwargs.get("shelf")

    inventory_item_table = sa.Table(
        "ref_stock_items",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("item_id", sa.UUID, sa.ForeignKey("ref_items.id"), nullable=False),
        sa.Column("shelf_id", sa.UUID, sa.ForeignKey("ref_shelves.id"), nullable=False),
        sa.Column("auction_start", sa.TIMESTAMP(timezone=True), nullable=True)
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

    item_tickets = sa.Table(
        "ref_bids",
        metadata,
        sa.Column("inventory_id", sa.UUID, sa.ForeignKey("ref_stock_items.id"), primary_key=True),
        sa.Column("character_id", sa.UUID, sa.ForeignKey("characters.id"), primary_key=True),
        sa.Column("bid", sa.Integer, nullable=False)

    )

    class ItemTicket(Schema):
        inventory_id = fields.UUID(required=True)
        character_id = fields.UUID(required=True)
        tickets = fields.Integer(required=True, data_key="bid")

        @post_load
        def make_ticket(self, data, **kwargs) -> dict:
            return data

    @property
    def bids(self):
        return self.tickets

    @bids.setter
    def bids(self, value):
        self.tickets = value

    async def delete(self):
        if not self.id:
            return

        ticket_query = (
            self.item_tickets.delete()
            .where(self.item_tickets.c.inventory_id == self.id)
        )
        await execute_query(self._db, ticket_query, QueryResultType.none)

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

        if self.tickets is not None:
            inv_item.tickets = self.tickets
            await inv_item.upsert_tickets(self.tickets)

        return inv_item

    async def upsert_tickets(self, tickets: dict[Union["Character", uuid.UUID, str], int]):
        from .character import Character

        if not self.id:
            return

        delete_query = (
            self.item_tickets.delete()
            .where(self.item_tickets.c.inventory_id == self.id)
        )
        await execute_query(self._db, delete_query, QueryResultType.none)

        if not tickets:
            # Null out auction_start if no tickets
            update_query = (
                self.inventory_item_table.update()
                .where(self.inventory_item_table.c.id == self.id)
                .values(auction_start=None)
            )
            await execute_query(self._db, update_query, QueryResultType.none)
            self.tickets = {}
            self.auction_start = None
            return

        normalized = []
        hydrated: dict["Character", int] = {}
        for character_or_id, quantity in tickets.items():
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
                    "bid": int(quantity),
                }
            )
            hydrated[character] = int(quantity)

        if normalized:
            update_query = (
                self.inventory_item_table.update()
                .where(self.inventory_item_table.c.id == self.id)
                .where(self.inventory_item_table.c.auction_start.is_(None))
                .values(auction_start=datetime.now(timezone.utc))
                .returning(self.inventory_item_table.c.auction_start)
            )
            updated = await execute_query(self._db, update_query)
            if updated:
                self.auction_start = updated._mapping.get("auction_start")

            insert_query = self.item_tickets.insert().values(normalized)
            await execute_query(self._db, insert_query, QueryResultType.none)

        self.tickets = hydrated

    async def load_tickets(self) -> dict["Character", int]:
        from .character import Character

        if not self.id:
            self.tickets = {}
            return self.tickets

        query = (
            self.item_tickets.select()
            .where(self.item_tickets.c.inventory_id == self.id)
            .order_by(self.item_tickets.c.bid.desc())
        )

        rows = await execute_query(self._db, query, QueryResultType.multiple)

        if not rows:
            self.tickets = {}
            return self.tickets

        tickets: dict["Character", int] = {}
        for row in rows:
            data = self.ItemTicket().load(dict(row._mapping))
            character = await Character.fetch(self._db, data["character_id"], active_only=False)
            if character:
                tickets[character] = data["tickets"]

        self.tickets = tickets
        return tickets

    async def upsert_bids(self, bids: dict[Union["Character", uuid.UUID, str], int]):
        await self.upsert_tickets(bids)

    async def load_bids(self) -> dict["Character", int]:
        return await self.load_tickets()

    @staticmethod
    async def fetch(db: AsyncEngine, inventory_id: Union[uuid.UUID, str], load_tickets: bool = True, load_item: bool = True, load_bids: Optional[bool] = None) -> Optional["StockItem"]:
        if isinstance(inventory_id, str):
            inventory_id = uuid.UUID(inventory_id)

        query = (
            StockItem.inventory_item_table.select()
            .where(StockItem.inventory_item_table.c.id == inventory_id)
        )

        row = await execute_query(db, query)

        if not row:
            return None

        stock_item = StockItem.InventoryItemSchema(db).load(dict(row._mapping))

        if load_item:
            stock_item.item = await Item.fetch(db, stock_item.item_id)

        if load_bids is not None:
            load_tickets = load_bids

        if load_tickets:
            await stock_item.load_tickets()

        return stock_item

    @staticmethod
    async def fetch_by_house(db: AsyncEngine, house_id: Union[uuid.UUID, str], load_tickets: bool = True, load_bids: Optional[bool] = None) -> list["StockItem"]:
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

        if load_bids is not None:
            load_tickets = load_bids

        if load_tickets:
            for item in items:
                await item.load_tickets()

        return items


class Raffle:
    def __init__(self, bot: "StewardBot", **kwargs):
        self._bot = bot

        self.id = kwargs.get("id")
        self.name = kwargs.get("name")
        self.guild_id = kwargs.get("guild_id")
        self.channel_id = kwargs.get("channel_id")
        self.message_id = kwargs.get("message_id")
        self.max_tickets = kwargs.get("max_tickets", kwargs.get("min_bid_percent", 0))
        self.raffle_length = kwargs.get("raffle_length", kwargs.get("auction_length"))
        self.ticket_cost_percent = kwargs.get("ticket_cost_percent", kwargs.get("reroll_interval", 0))
        self.action_log_activity_name = kwargs.get("raffle_log_activity_name", kwargs.get("auction_log_activity_name"))

        # Post Load Items
        self.items: list["Item"] = kwargs.get("items", [])
        self.inventory: list["StockItem"] = kwargs.get("inventory", [])
        self.shelves: list["Shelf"] = kwargs.get("shelves", [])

    house_table = sa.Table(
        "ref_auction_houses",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers.id"), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("min_bid_percent", sa.DECIMAL(), nullable=True),
        sa.Column("auction_length", sa.DECIMAL(), nullable=True),
        sa.Column("reroll_interval", sa.DECIMAL(), nullable=True),
        sa.Column("action_log_activity_name", sa.String(), nullable=True)
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
    
    class RaffleSchema(Schema):
        bot: "StewardBot"

        id = fields.UUID(required=False, allow_none=True)
        name = fields.String(required=True)
        guild_id = fields.Integer(required=True)
        channel_id = fields.Integer(required=True)
        message_id = fields.Integer(required=True)
        type = fields.String(required=False, allow_none=True)
        max_tickets = fields.Float(required=False, allow_none=True, data_key="min_bid_percent")
        raffle_length = fields.Float(required=False, allow_none=True, data_key="auction_length")
        ticket_cost_percent = fields.Float(required=False, allow_none=True, data_key="reroll_interval")
        action_log_activity_name = fields.String(required=False, allow_none=True)

        def __init__(self, bot: "StewardBot", **kwargs):
            super().__init__(**kwargs)
            self.bot = bot

        @post_load
        def make_house(self, data, **kwargs):
            return Raffle(self.bot, **data)

    async def delete(self):
        if not self.id:
            return

        query = (
            self.house_table.delete()
            .where(self.house_table.c.id == self.id)
        )

        await execute_query(self._bot.db, query, QueryResultType.none)

    async def upsert(self) -> "Raffle":
        update_dict = {
            "name": self.name,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "min_bid_percent": self.max_tickets,
            "auction_length": self.raffle_length,
            "reroll_interval": self.ticket_cost_percent,
            "action_log_activity_name": self.action_log_activity_name
        }

        if self.id:
            query = (
                self.house_table.update()
                .where(self.house_table.c.id == self.id)
                .values(**update_dict)
                .returning(self.house_table)
            )
        else:
            query = (
                self.house_table.insert()
                .values(**update_dict)
                .returning(self.house_table)
            )

        row = await execute_query(self._bot.db, query)

        if not row:
            return self

        return self.RaffleSchema(self._bot).load(dict(row._mapping))

    @staticmethod
    async def fetch(bot: "StewardBot", guild_id: int, load_related: bool = True) -> Union["Raffle", None]:
        query = (
            Raffle.house_table.select()
            .where(Raffle.house_table.c.guild_id == guild_id)
            .order_by(Raffle.house_table.c.name)
            .limit(1)
        )

        row = await execute_query(bot.db, query)

        if not row:
            return None

        house = Raffle.RaffleSchema(bot).load(dict(row._mapping))

        if load_related:
            await Raffle._load_related(bot, house)

        return house

    @staticmethod
    async def fetch_by_id(bot: "StewardBot", house_id: Union[uuid.UUID, str], load_related: bool = True) -> Union["Raffle", None]:
        if isinstance(house_id, str):
            house_id = uuid.UUID(house_id)

        query = (
            Raffle.house_table.select()
            .where(Raffle.house_table.c.id == house_id)
        )

        row = await execute_query(bot.db, query)

        if not row:
            return None

        house = Raffle.RaffleSchema(bot).load(dict(row._mapping))

        if load_related:
            await Raffle._load_related(bot, house)

        return house

    @staticmethod
    async def fetch_all(bot: "StewardBot", load_related: bool = True) -> list["Raffle"]:
        query = (
            Raffle.house_table.select()
            .order_by(Raffle.house_table.c.name)
        )

        rows = await execute_query(bot.db, query, QueryResultType.multiple)

        if not rows:
            return []

        houses = [Raffle.RaffleSchema(bot).load(dict(row._mapping)) for row in rows]

        if load_related:
            for house in houses:
                await Raffle._load_related(bot, house)

        return houses

    @staticmethod
    async def _load_related(bot: "StewardBot", house: "Raffle"):
        house.items = await Item.fetch_by_house(bot.db, house.id)
        house.shelves = await Shelf.fetch_by_house(bot.db, house.id)
        house.inventory = await StockItem.fetch_by_house(bot.db, house.id, load_tickets=True)

        items_by_id = {item.id: item for item in house.items}
        shelves_by_id = {shelf.id: shelf for shelf in house.shelves}

        for inv_item in house.inventory:
            inv_item.item = items_by_id.get(inv_item.item_id)
            inv_item.shelf = shelves_by_id.get(inv_item.shelf_id)

        # Populate shelf inventory items
        for shelf in house.shelves:
            shelf.items = [inv for inv in house.inventory if inv.shelf_id == shelf.id]

    def ticket_cost(self, item: "Item") -> int:
        cost = (item.cost or 0) * ((self.ticket_cost_percent or 0) / 100)
        return max(0, int(round(cost)))

    def tickets_sold(self, inventory_item: "StockItem") -> int:
        return sum((inventory_item.tickets or {}).values())

    def tickets_remaining(self, inventory_item: "StockItem") -> Optional[int]:
        if self.max_tickets in (None, 0):
            return None
        return max(0, int(self.max_tickets) - self.tickets_sold(inventory_item))
    
    def next_reroll_at(self):
        return None
    
    def raffle_end_at(self, inventory_item: "StockItem"):
        if not inventory_item.auction_start:
            return None

        if not self.raffle_length:
            return None
        return inventory_item.auction_start + timedelta(hours=float(self.raffle_length))

    async def purchase_tickets(self, inventory_item: "StockItem", character: "Character", quantity: int = 1) -> tuple[bool, str]:
        if quantity <= 0:
            return False, "Ticket quantity must be positive."

        item = inventory_item.item or next((itm for itm in self.items if itm.id == inventory_item.item_id), None)
        if not item:
            return False, "Item not found."

        if character in (inventory_item.tickets or {}):
            return False, "You already purchased tickets for this item."

        remaining = self.tickets_remaining(inventory_item)
        if remaining is not None and quantity > remaining:
            return False, f"Only {remaining} ticket(s) remain for this item."

        unit_cost = self.ticket_cost(item)
        total_cost = unit_cost * quantity

        if character.currency < total_cost:
            return False, f"Insufficient funds. Need {total_cost:,}, you have {character.currency:,}."

        from Steward.models.objects.log import StewardLog
        from .player import Player

        if self.action_log_activity_name and self.action_log_activity_name != "":
            member = self.guild.get_member(character.player_id)
            winning_player = await Player.get_or_create(self._bot.db, member)
            await StewardLog.create(
                self._bot,
                self._bot.user,
                winning_player,
                LogEvent.automation,
                activity=self.action_log_activity_name,
                currency=-total_cost,
                character=character,
                notes=f"Raffle ticket purchase: {item.name} ({quantity})"
            )

        if not inventory_item.tickets:
            inventory_item.tickets = {}

        inventory_item.tickets[character] = quantity
        await inventory_item.upsert_tickets(inventory_item.tickets)

        return True, f"Purchased {quantity} ticket(s) for {item.name}."

    async def finalize_raffle(self, inventory_item: "StockItem", reason: str):
        from Steward.models.objects.log import StewardLog
        from .player import Player

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
        
        tickets = dict(inventory_item.tickets or {})

        if not tickets:
            await inventory_item.delete()
            await self.refresh_view()
            return

        ticket_price = self.ticket_cost(item)
        weighted_pool: list["Character"] = []
        for character, qty in tickets.items():
            weighted_pool.extend([character] * max(0, int(qty)))

        if not weighted_pool:
            await inventory_item.delete()
            await self.refresh_view()
            return

        winner = random.choice(weighted_pool)
        winner_ticket_qty = int(tickets.get(winner, 0))
        remaining_cost = max(0, int(round(item.cost or 0)) - (winner_ticket_qty * ticket_price))

        if winner.currency < remaining_cost:
            eligible: list["Character"] = []
            for character, qty in tickets.items():
                char_remaining = max(0, int(round(item.cost or 0)) - (int(qty) * ticket_price))
                if character.currency >= char_remaining:
                    eligible.extend([character] * int(qty))

            if eligible:
                winner = random.choice(eligible)
                winner_ticket_qty = int(tickets.get(winner, 0))
                remaining_cost = max(0, int(round(item.cost or 0)) - (winner_ticket_qty * ticket_price))
            else:
                winner = None

        if winner is not None:
            if self.action_log_activity_name and self.action_log_activity_name != "":
                member = self.guild.get_member(winner.player_id)
                winning_player = await Player.get_or_create(self._bot.db, member)
                await StewardLog.create(
                    self._bot,
                    self._bot.user,
                    winning_player,
                    LogEvent.automation,
                    activity=self.action_log_activity_name,
                    currency=-remaining_cost,
                    character=winner,
                    notes=f"Raffle won: {item.name}"
                )
            tickets_snapshot = sorted(tickets.items(), key=lambda pair: pair[1], reverse=True)
            self._bot.dispatch(RuleTrigger.raffle_complete.name, item, winner, remaining_cost, tickets_snapshot, reason)
            self._bot.dispatch(RuleTrigger.auction_complete.name, item, winner, remaining_cost, tickets_snapshot, reason)
        await inventory_item.delete()

        await self.refresh_view()

    async def finalize_item(self, inventory_item: "StockItem", reason: str):
        await self.finalize_raffle(inventory_item, reason)

    def auction_end_at(self, inventory_item: "StockItem"):
        return self.raffle_end_at(inventory_item)

    async def refresh_view(self):
        from ..views.raffleHouse import RaffleView

        if not self.message_id:
            return
        
        view = RaffleView(self)

        message = await self.channel.fetch_message(self.message_id)

        if message:
            await message.edit(view=view)

    async def reroll_inventory(self):
        house = await self.fetch_by_id(self._bot, self.id)

        if not house.shelves or not house.items:
            await house.refresh_view()
            return
        
        shelves = sorted(house.shelves, key=lambda shelf: shelf.priority)
        remaining_slots = {shelf.id: max(0, int(shelf.max_qty or 0)) for shelf in shelves}
        item_counts = {item.id: 0 for item in house.items}
        placements = []

        # Pass 1 - Initial Load
        for item in house.items:
            min_qty = max(0, int(item.min_qty or 0))
            for _ in range(min_qty):
                eligible_shelves = [shelf for shelf in shelves if remaining_slots[shelf.id] > 0]
                if not eligible_shelves:
                    break

                shelf = random.choice(eligible_shelves)
                placements.append((item.id, shelf.id))
                remaining_slots[shelf.id] -= 1
                item_counts[item.id] += 1

        # Pass 2 - Fill in gaps
        for shelf in shelves:
            while remaining_slots[shelf.id] > 0:
                eligible_items = [
                    item for item in house.items
                    if item.max_qty is None or item_counts[item.id] < int(item.max_qty)
                ]

                if not eligible_items:
                    break

                item = random.choice(eligible_items)
                placements.append((item.id, shelf.id))
                remaining_slots[shelf.id] -= 1
                item_counts[item.id] += 1

            for item_id, shelf_id in placements:
                inv = StockItem(self._bot.db, item_id=item_id, shelf_id=shelf_id)
                await inv.upsert()

            house = await self.fetch_by_id(self._bot, house.id)
            await house.refresh_view()


AuctionHouse = Raffle
RaffleSchema = Raffle.RaffleSchema


        
    
            

        




        
    







from datetime import datetime, timedelta, timezone
import random
from typing import TYPE_CHECKING, Optional, Union
import sqlalchemy as sa
import uuid

from marshmallow import Schema, fields, post_load
from sqlalchemy.ext.asyncio import AsyncEngine

from Steward.models.objects.enum import QueryResultType

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
        self.guild_id = kwargs.get("guild_id")
        self.shop_keys = kwargs.get("shop_keys", [])
        self.name = kwargs.get("name")
        self.description = kwargs.get("description")
        self.category = kwargs.get("category")
        self.cost = kwargs.get("cost", 1)
        self.max_qty = kwargs.get("max_qty")

    item_table = sa.Table(
        "ref_shop_items",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers.id"), nullable=False),
        sa.Column("shop_keys", sa.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.String, nullable=True),
        sa.Column("category", sa.String, nullable=True),
        sa.Column("cost", sa.Float, nullable=False, server_default="1"),
        sa.Column("max_qty", sa.Integer, nullable=True),
    )

    class ItemSchema(Schema):
        db: AsyncEngine

        id = fields.UUID(required=True, allow_none=False)
        guild_id = fields.Integer(required=True, allow_none=False)
        shop_keys = fields.List(fields.String, load_default=list)
        name = fields.String(required=True)
        description = fields.String(allow_none=True, load_default=None)
        category = fields.String(allow_none=True, load_default=None)
        cost = fields.Float(required=True, allow_none=False)
        max_qty = fields.Integer(allow_none=True, load_default=None)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db

        @post_load
        def make_item(self, data, **kwargs):
            return Item(self.db, **data)

    async def delete(self):
        if not self.id:
            return

        query = self.item_table.delete().where(self.item_table.c.id == self.id)
        await execute_query(self._db, query, QueryResultType.none)

    async def upsert(self) -> "Item":
        update_dict = {
            "shop_keys": self.shop_keys,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "cost": self.cost,
            "max_qty": self.max_qty,
        }
        insert_dict = {"guild_id": self.guild_id, **update_dict}

        if self.id is not None:
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
        return self.ItemSchema(self._db).load(dict(result._mapping))

    @staticmethod
    async def fetch(db: AsyncEngine, item_id: Union[uuid.UUID, str]) -> Optional["Item"]:
        if isinstance(item_id, str):
            item_id = uuid.UUID(item_id)

        query = Item.item_table.select().where(Item.item_table.c.id == item_id)
        row = await execute_query(db, query)
        if not row:
            return None
        return Item.ItemSchema(db).load(dict(row._mapping))

    @staticmethod
    async def fetch_by_guild(db: AsyncEngine, guild_id: int) -> list["Item"]:
        query = (
            Item.item_table.select()
            .where(Item.item_table.c.guild_id == guild_id)
            .order_by(Item.item_table.c.name)
        )
        rows = await execute_query(db, query, QueryResultType.multiple)
        if not rows:
            return []
        return [Item.ItemSchema(db).load(dict(row._mapping)) for row in rows]

    @staticmethod
    async def fetch_by_shop(db: AsyncEngine, shop_key: str, guild_id: int) -> list["Item"]:
        query = (
            Item.item_table.select()
            .where(
                sa.and_(
                    Item.item_table.c.guild_id == guild_id,
                    Item.item_table.c.shop_keys.contains([shop_key]),
                )
            )
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
        self.shop_id = kwargs.get("shop_id")
        self.priority = kwargs.get("priority", 0)
        self.description = kwargs.get("description")
        self.max_qty = kwargs.get("max_qty", 1)

        self.items: list["StockItem"] = kwargs.get("items", [])

    shelf_table = sa.Table(
        "ref_shop_shelves",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("shop_id", sa.UUID, sa.ForeignKey("ref_shops.id"), nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("description", sa.String, nullable=True),
        sa.Column("max_qty", sa.Integer, nullable=False, server_default="1"),
    )

    class ShelfSchema(Schema):
        db: AsyncEngine

        id = fields.UUID(required=True, allow_none=False)
        shop_id = fields.UUID(required=True)
        priority = fields.Integer(load_default=0)
        description = fields.String(allow_none=True, load_default=None)
        max_qty = fields.Integer(load_default=1)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db

        @post_load
        def make_shelf(self, data, **kwargs):
            return Shelf(self.db, **data)

    async def delete(self):
        if not self.id:
            return
        query = self.shelf_table.delete().where(self.shelf_table.c.id == self.id)
        await execute_query(self._db, query, QueryResultType.none)

    async def upsert(self) -> "Shelf":
        update_dict = {
            "priority": self.priority,
            "description": self.description,
            "max_qty": self.max_qty,
        }
        insert_dict = {"shop_id": self.shop_id, **update_dict}

        if self.id is not None:
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
        return self.ShelfSchema(self._db).load(dict(result._mapping))

    @staticmethod
    async def fetch_by_shop(db: AsyncEngine, shop_id: Union[uuid.UUID, str]) -> list["Shelf"]:
        if isinstance(shop_id, str):
            shop_id = uuid.UUID(shop_id)

        query = (
            Shelf.shelf_table.select()
            .where(Shelf.shelf_table.c.shop_id == shop_id)
            .order_by(Shelf.shelf_table.c.priority, Shelf.shelf_table.c.id)
        )
        rows = await execute_query(db, query, QueryResultType.multiple)
        if not rows:
            return []
        return [Shelf.ShelfSchema(db).load(dict(row._mapping)) for row in rows]


class RaffleTicket:
    def __init__(self, db: AsyncEngine, **kwargs):
        self._db = db

        self.stock_item_id = kwargs.get("stock_item_id")
        self.character_id = kwargs.get("character_id")
        self.quantity = kwargs.get("quantity", 1)

        self.character: Optional["Character"] = kwargs.get("character")

    ticket_table = sa.Table(
        "ref_raffle_tickets",
        metadata,
        sa.Column("stock_item_id", sa.UUID, sa.ForeignKey("ref_shop_stock.id"), primary_key=True),
        sa.Column("character_id", sa.UUID, sa.ForeignKey("characters.id"), primary_key=True),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
    )

    class RaffleTicketSchema(Schema):
        stock_item_id = fields.UUID(required=True)
        character_id = fields.UUID(required=True)
        quantity = fields.Integer(load_default=1)

        @post_load
        def make_ticket(self, data, **kwargs) -> dict:
            return data

    async def upsert(self, db: AsyncEngine) -> "RaffleTicket":
        update_query = (
            self.ticket_table.update()
            .where(
                sa.and_(
                    self.ticket_table.c.stock_item_id == self.stock_item_id,
                    self.ticket_table.c.character_id == self.character_id,
                )
            )
            .values(quantity=self.quantity)
            .returning(self.ticket_table)
        )
        result = await execute_query(db, update_query)

        if not result:
            insert_query = (
                self.ticket_table.insert()
                .values(
                    stock_item_id=self.stock_item_id,
                    character_id=self.character_id,
                    quantity=self.quantity,
                )
                .returning(self.ticket_table)
            )
            result = await execute_query(db, insert_query)

        if result:
            data = RaffleTicket.RaffleTicketSchema().load(dict(result._mapping))
            self.quantity = data["quantity"]

        return self


class StockItem:
    def __init__(self, db: AsyncEngine, **kwargs):
        self._db = db

        self.id = kwargs.get("id")
        self.item_id = kwargs.get("item_id")
        self.shelf_id = kwargs.get("shelf_id")
        self.raffle_start = kwargs.get("raffle_start")

        self.item: Optional["Item"] = kwargs.get("item")
        self.shelf: Optional["Shelf"] = kwargs.get("shelf")
        self.tickets: list["RaffleTicket"] = kwargs.get("tickets", [])

    stock_table = sa.Table(
        "ref_shop_stock",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("item_id", sa.UUID, sa.ForeignKey("ref_shop_items.id"), nullable=False),
        sa.Column("shelf_id", sa.UUID, sa.ForeignKey("ref_shop_shelves.id"), nullable=False),
        sa.Column("raffle_start", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    class StockItemSchema(Schema):
        db: AsyncEngine

        id = fields.UUID(required=True)
        item_id = fields.UUID(required=True)
        shelf_id = fields.UUID(required=True)
        raffle_start = fields.DateTime(allow_none=True, load_default=None)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db

        @post_load
        def make_stock_item(self, data, **kwargs):
            return StockItem(self.db, **data)

    async def delete(self):
        if not self.id:
            return

        ticket_query = (
            RaffleTicket.ticket_table.delete()
            .where(RaffleTicket.ticket_table.c.stock_item_id == self.id)
        )
        await execute_query(self._db, ticket_query, QueryResultType.none)

        query = self.stock_table.delete().where(self.stock_table.c.id == self.id)
        await execute_query(self._db, query, QueryResultType.none)

    async def upsert(self) -> "StockItem":
        update_dict = {
            "item_id": self.item_id,
            "shelf_id": self.shelf_id,
            "raffle_start": self.raffle_start,
        }

        if self.id is not None:
            query = (
                self.stock_table.update()
                .values(**update_dict)
                .where(self.stock_table.c.id == self.id)
                .returning(self.stock_table)
            )
        else:
            query = (
                self.stock_table.insert()
                .values(**update_dict)
                .returning(self.stock_table)
            )

        result = await execute_query(self._db, query)
        if not result:
            return self
        return self.StockItemSchema(self._db).load(dict(result._mapping))

    async def load_tickets(self) -> list["RaffleTicket"]:
        from .character import Character

        if not self.id:
            self.tickets = []
            return self.tickets

        query = (
            RaffleTicket.ticket_table.select()
            .where(RaffleTicket.ticket_table.c.stock_item_id == self.id)
        )
        rows = await execute_query(self._db, query, QueryResultType.multiple)

        if not rows:
            self.tickets = []
            return self.tickets

        tickets = []
        for row in rows:
            data = RaffleTicket.RaffleTicketSchema().load(dict(row._mapping))
            ticket = RaffleTicket(self._db, **data)
            ticket.character = await Character.fetch(self._db, data["character_id"], active_only=False)
            tickets.append(ticket)

        self.tickets = tickets
        return tickets

    @staticmethod
    async def fetch(db: AsyncEngine, stock_id: Union[uuid.UUID, str], load_tickets: bool = True) -> Optional["StockItem"]:
        if isinstance(stock_id, str):
            stock_id = uuid.UUID(stock_id)

        query = StockItem.stock_table.select().where(StockItem.stock_table.c.id == stock_id)
        row = await execute_query(db, query)
        if not row:
            return None

        stock = StockItem.StockItemSchema(db).load(dict(row._mapping))
        if load_tickets:
            await stock.load_tickets()
        return stock

    @staticmethod
    async def fetch_by_shop(db: AsyncEngine, shop_id: Union[uuid.UUID, str], load_tickets: bool = False) -> list["StockItem"]:
        if isinstance(shop_id, str):
            shop_id = uuid.UUID(shop_id)

        query = (
            StockItem.stock_table
            .select()
            .join(Shelf.shelf_table, StockItem.stock_table.c.shelf_id == Shelf.shelf_table.c.id)
            .where(Shelf.shelf_table.c.shop_id == shop_id)
            .order_by(Shelf.shelf_table.c.priority, StockItem.stock_table.c.raffle_start)
        )
        rows = await execute_query(db, query, QueryResultType.multiple)
        if not rows:
            return []

        items = [StockItem.StockItemSchema(db).load(dict(row._mapping)) for row in rows]
        if load_tickets:
            for item in items:
                await item.load_tickets()
        return items


class Shop:
    def __init__(self, bot: "StewardBot", **kwargs):
        self._bot = bot

        self.id = kwargs.get("id")
        self.key = kwargs.get("key")
        self.name = kwargs.get("name")
        self.description = kwargs.get("description")
        self.guild_id = kwargs.get("guild_id")
        self.channel_id = kwargs.get("channel_id")
        self.message_id = kwargs.get("message_id")
        self.ticket_cost = kwargs.get("ticket_cost", 1)
        self.max_tickets = kwargs.get("max_tickets", 1)
        self.raffle_duration = kwargs.get("raffle_duration")  # hours

        self.items: list["Item"] = kwargs.get("items", [])
        self.stock: list["StockItem"] = kwargs.get("stock", [])
        self.shelves: list["Shelf"] = kwargs.get("shelves", [])

    shop_table = sa.Table(
        "ref_shops",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("key", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.String, nullable=True),
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers.id"), nullable=False),
        sa.Column("channel_id", sa.BigInteger, nullable=False),
        sa.Column("message_id", sa.BigInteger, nullable=True),
        sa.Column("ticket_cost", sa.Float, nullable=False, server_default="1"),
        sa.Column("max_tickets", sa.Integer, nullable=False, server_default="1"),
        sa.Column("raffle_duration", sa.Float, nullable=True),
    )

    class ShopSchema(Schema):
        bot: "StewardBot"

        id = fields.UUID(required=True, allow_none=False)
        key = fields.String(required=True)
        name = fields.String(required=True)
        description = fields.String(allow_none=True, load_default=None)
        guild_id = fields.Integer(required=True)
        channel_id = fields.Integer(required=True)
        message_id = fields.Integer(allow_none=True, load_default=None)
        ticket_cost = fields.Float(load_default=1)
        max_tickets = fields.Integer(load_default=1)
        raffle_duration = fields.Float(allow_none=True, load_default=None)

        def __init__(self, bot: "StewardBot", **kwargs):
            super().__init__(**kwargs)
            self.bot = bot

        @post_load
        def make_shop(self, data, **kwargs):
            return Shop(self.bot, **data)

    @property
    def guild(self):
        return self._bot.get_guild(self.guild_id)

    @property
    def channel(self):
        guild = self.guild
        if not guild:
            return None
        return guild.get_channel(self.channel_id)

    def raffle_end_at(self, stock_item: "StockItem") -> Optional[datetime]:
        if not stock_item.raffle_start or not self.raffle_duration:
            return None
        return stock_item.raffle_start + timedelta(hours=float(self.raffle_duration))

    async def delete(self):
        if not self.id:
            return
        query = self.shop_table.delete().where(self.shop_table.c.id == self.id)
        await execute_query(self._bot.db, query, QueryResultType.none)

    async def upsert(self) -> "Shop":
        update_dict = {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "ticket_cost": self.ticket_cost,
            "max_tickets": self.max_tickets,
            "raffle_duration": self.raffle_duration,
        }

        if self.id is not None:
            query = (
                self.shop_table.update()
                .values(**update_dict)
                .where(self.shop_table.c.id == self.id)
                .returning(self.shop_table)
            )
        else:
            query = (
                self.shop_table.insert()
                .values(**update_dict)
                .returning(self.shop_table)
            )

        row = await execute_query(self._bot.db, query)
        if not row:
            return self
        return self.ShopSchema(self._bot).load(dict(row._mapping))

    @staticmethod
    async def fetch_all(bot: "StewardBot", load_related: bool = True) -> list["Shop"]:
        query = Shop.shop_table.select().order_by(Shop.shop_table.c.name)
        rows = await execute_query(bot.db, query, QueryResultType.multiple)
        if not rows:
            return []

        shops = [Shop.ShopSchema(bot).load(dict(row._mapping)) for row in rows]
        if load_related:
            for shop in shops:
                await Shop._load_related(bot, shop)
        return shops

    @staticmethod
    async def fetch_by_guild(bot: "StewardBot", guild_id: int, load_related: bool = True) -> list["Shop"]:
        query = (
            Shop.shop_table.select()
            .where(Shop.shop_table.c.guild_id == guild_id)
            .order_by(Shop.shop_table.c.name)
        )
        rows = await execute_query(bot.db, query, QueryResultType.multiple)
        if not rows:
            return []

        shops = [Shop.ShopSchema(bot).load(dict(row._mapping)) for row in rows]
        if load_related:
            for shop in shops:
                await Shop._load_related(bot, shop)
        return shops

    @staticmethod
    async def fetch_by_id(bot: "StewardBot", shop_id: Union[uuid.UUID, str], load_related: bool = True) -> Optional["Shop"]:
        if isinstance(shop_id, str):
            shop_id = uuid.UUID(shop_id)

        query = Shop.shop_table.select().where(Shop.shop_table.c.id == shop_id)
        row = await execute_query(bot.db, query)
        if not row:
            return None

        shop = Shop.ShopSchema(bot).load(dict(row._mapping))
        if load_related:
            await Shop._load_related(bot, shop)
        return shop

    @staticmethod
    async def _load_related(bot: "StewardBot", shop: "Shop"):
        shop.items = await Item.fetch_by_shop(bot.db, shop.key, shop.guild_id)
        shop.shelves = await Shelf.fetch_by_shop(bot.db, shop.id)
        shop.stock = await StockItem.fetch_by_shop(bot.db, shop.id, load_tickets=True)

        items_by_id = {item.id: item for item in shop.items}
        shelves_by_id = {shelf.id: shelf for shelf in shop.shelves}

        for stock in shop.stock:
            stock.item = items_by_id.get(stock.item_id)
            stock.shelf = shelves_by_id.get(stock.shelf_id)

        for shelf in shop.shelves:
            shelf.items = [s for s in shop.stock if s.shelf_id == shelf.id]

    async def refresh_view(self):
        from ..views.market import ShopView

        if not self.message_id:
            return

        shop = await Shop.fetch_by_id(self._bot, self.id)
        if not shop:
            return

        view = ShopView(shop)
        message = await shop.channel.fetch_message(shop.message_id)
        if message:
            await message.edit(view=view)

    async def reroll_inventory(self):
        """Finalize all active raffles and stock fresh inventory on the shelves."""
        shop = await Shop.fetch_by_id(self._bot, self.id, load_related=True)
        if not shop:
            return

        for stock in list(shop.stock):
            await shop.finalize_raffle(stock, "Inventory Rerolled")

        # Reload after clearing old stock
        shop = await Shop.fetch_by_id(self._bot, self.id, load_related=True)

        if not shop.shelves or not shop.items:
            await shop.refresh_view()
            return

        shelves = sorted(shop.shelves, key=lambda s: s.priority)
        remaining_slots = {shelf.id: max(0, int(shelf.max_qty or 0)) for shelf in shelves}
        item_counts = {item.id: 0 for item in shop.items}
        placements: list[tuple[uuid.UUID, uuid.UUID]] = []

        for shelf in shelves:
            while remaining_slots[shelf.id] > 0:
                eligible = [
                    item for item in shop.items
                    if item.max_qty is None or item_counts[item.id] < int(item.max_qty)
                ]
                if not eligible:
                    break
                item = random.choice(eligible)
                placements.append((item.id, shelf.id))
                remaining_slots[shelf.id] -= 1
                item_counts[item.id] += 1

        now = datetime.now(timezone.utc)
        for item_id, shelf_id in placements:
            stock = StockItem(self._bot.db, item_id=item_id, shelf_id=shelf_id, raffle_start=now)
            await stock.upsert()

        shop = await Shop.fetch_by_id(self._bot, self.id, load_related=True)
        self.stock = shop.stock
        self.shelves = shop.shelves
        await shop.refresh_view()

    async def buy_ticket(self, stock_item: "StockItem", character: "Character", quantity: int = 1) -> tuple[bool, str]:
        """Purchase raffle tickets for a character on a stocked item.

        Returns a (success, message) tuple.
        """
        from .character import Character as CharacterModel

        existing = next((t for t in stock_item.tickets if t.character_id == character.id), None)
        current_qty = existing.quantity if existing else 0
        available = self.max_tickets - current_qty

        if available <= 0:
            return False, f"You've already purchased the maximum of {self.max_tickets} ticket(s) for this item."

        if quantity > available:
            return False, f"You can only buy {available} more ticket(s) (max {self.max_tickets} per item)."

        total_cost = self.ticket_cost * quantity
        if float(character.currency) < total_cost:
            return False, (
                f"Not enough currency. Cost: {total_cost:,.0f}, "
                f"available: {float(character.currency):,.0f}."
            )

        deduct_query = (
            CharacterModel.characters_table.update()
            .where(CharacterModel.characters_table.c.id == character.id)
            .values(currency=CharacterModel.characters_table.c.currency - total_cost)
            .returning(CharacterModel.characters_table.c.currency)
        )
        result = await execute_query(self._bot.db, deduct_query)
        if result:
            character.currency = result._mapping.get("currency", character.currency)

        ticket = RaffleTicket(
            self._bot.db,
            stock_item_id=stock_item.id,
            character_id=character.id,
            quantity=current_qty + quantity,
        )
        await ticket.upsert(self._bot.db)
        await stock_item.load_tickets()

        item_name = stock_item.item.name if stock_item.item else "item"
        return True, (
            f"Purchased {quantity} ticket(s) for **{item_name}**! "
            f"Total cost: {total_cost:,.0f}. "
            f"You now hold {current_qty + quantity} ticket(s)."
        )

    async def finalize_raffle(self, stock_item: "StockItem", reason: str):
        """Draw a winner from all purchased tickets and clean up the stock item."""
        reloaded = await StockItem.fetch(self._bot.db, stock_item.id, load_tickets=True)
        if not reloaded:
            return

        item = next((i for i in self.items if i.id == reloaded.item_id), None)
        if not item:
            item = await Item.fetch(self._bot.db, reloaded.item_id)

        entries: list["Character"] = []
        for ticket in reloaded.tickets:
            if ticket.character:
                entries.extend([ticket.character] * ticket.quantity)

        winner = random.choice(entries) if entries else None

        if winner and item:
            self._bot.dispatch("raffle_complete", self, item, winner, reloaded.tickets, reason)

        await reloaded.delete()

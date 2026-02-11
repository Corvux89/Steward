from typing import TYPE_CHECKING
import sqlalchemy as sa
import uuid
import discord

from marshmallow import Schema, fields

from Steward.models.objects.enum import QueryResultType

from ...models import metadata
from ...utils.dbUtils import execute_query

if TYPE_CHECKING:
    from ...bot import StewardBot

class CategoryDashboard:
    def __init__(self, bot: "StewardBot", **kwargs):
        self._bot = bot

        self.id = kwargs.get("id")
        self.guild_id = kwargs.get("guild_id")
        self.channel_id = kwargs.get("channel_id")
        self.category_id = kwargs.get("category_id")
        self.message_id = kwargs.get("message_id")
        self.excluded_channel_ids = kwargs.get("excluded_channel_ids", [])
    
        self._message: discord.Message = kwargs.get("_message")

    @property
    def guild(self):
        return self._bot.get_guild(self.guild_id)
    
    @property
    def category(self):
        return self.guild.get_channel(self.category_id)
    
    @property
    def channel(self):
        return self.guild.get_channel_or_thread(self.channel_id)
    
    @property
    def excluded_channels(self):
        return [self.guild.get_channel_or_thread(c) for c in self.excluded_channel_ids if self.guild.get_channel_or_thread(c)]
    
    @property
    def channels(self):
        if self.category:
            return list(
                filter(
                    lambda c: c.id not in self.excluded_channel_ids,
                    self.category.text_channels
                )
            )
        
        return []
    
    async def message(self) -> discord.Message:
        if not self._message:        
            try:
                self._message = await self.channel.fetch_message(self.message_id)
            except discord.HTTPException:
                return True
            except:
                return None
        return self._message
    
    category_dashboard_table = sa.Table(
        "ref_category_dashboards",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("guild_id", sa.BigInteger, nullable=False),
        sa.Column("channel_id", sa.BigInteger, nullable=False),
        sa.Column("category_id", sa.BigInteger, nullable=False),
        sa.Column("message_id", sa.BigInteger, nullable=False),
        sa.Column("excluded_channel_ids", sa.ARRAY(sa.BigInteger), nullable=False, default=[])
    )

    class CategoryDashboardSchema(Schema):
        id = fields.UUID(required=True)
        guild_id = fields.Integer(required=True)
        channel_id = fields.Integer(required=True)
        category_id = fields.Integer(required=True)
        message_id = fields.Integer(required=True)
        excluded_channel_ids = fields.List(fields.Integer, required=True)

    async def delete(self) -> None:
        query = (
            self.category_dashboard_table.delete()
            .where(self.category_dashboard_table.c.id == self.id)
        )

        await execute_query(self._bot.db, query, QueryResultType.none)

    async def upsert(self) -> "CategoryDashboard":
        update_dict = {
            "excluded_channel_ids": self.excluded_channel_ids
        }

        insert_dict = {
            "guild_id": self.guild_id,
            "category_id": self.category_id,
            "message_id": self.message_id,
            "channel_id": self.channel_id,
            **update_dict
        }

        if hasattr(self, "id") and self.id is not None:
            query = (
                self.category_dashboard_table.update()
                .where(self.category_dashboard_table.c.id == self.id)
                .values(**update_dict)
                .returning(self.category_dashboard_table)
            )
        else:
            query = (
                self.category_dashboard_table.insert()
                .values(**insert_dict)
                .returning(self.category_dashboard_table)
            )

        result = await execute_query(self._bot.db, query)

        if self.id is None and result:
            row = result[0] if isinstance(result, list) else result
            self.id = dict(row._mapping)["id"]

        return self
    
    @classmethod
    async def fetch(cls, bot: "StewardBot", category_id: int) -> list["CategoryDashboard"]:
        query = (
            cls.category_dashboard_table.select()
            .where(cls.category_dashboard_table.c.category_id == category_id)
        )

        row = rows = await execute_query(bot.db, query, QueryResultType.multiple)

        if not rows:
            return []
        
        if not isinstance(rows, list):
            rows = [rows]

        dashboards = []

        for row in rows:
            data = dict(row._mapping)
            dashboard = cls(bot, **data)

            dashboards.append(dashboard)

        return dashboards

    @classmethod
    async def fetch_all(cls, bot: "StewardBot", guild_id: int = None) -> list["CategoryDashboard"]:
        query = (
            cls.category_dashboard_table.select()
        )

        if guild_id:
            query = query.where(cls.category_dashboard_table.c.guild_id == guild_id)

        rows = await execute_query(bot.db, query, QueryResultType.multiple)

        if not rows:
            return []
        
        if not isinstance(rows, list):
            rows = [rows]

        dashboards = []

        for row in rows:
            data = dict(row._mapping)
            dashboard = cls(bot, **data)

            dashboards.append(dashboard)

        return dashboards
    
    async def refresh(self, message: discord.Message = None):
        from ..views.dashboards import CategoryDashboardView
        view = CategoryDashboardView(self)
        await view.refresh_dashboard(message)



from typing import Union
import uuid
import sqlalchemy as sa

from decimal import Decimal
from marshmallow import Schema, fields, post_load
from sqlalchemy.dialects.postgresql import ARRAY, insert
from sqlalchemy.ext.asyncio import AsyncEngine
from Steward.models import metadata
from Steward.utils.dbUtils import execute_query


class Activity:
    def __init__(self, db: AsyncEngine, **kwargs):
        self._db = db
        self.id = kwargs.get("id")
        self.guild_id = kwargs.get("guild_id")
        self.name = kwargs.get("name")

        self.currency_expr = kwargs.get("currency_expr")
        self.xp_expr = kwargs.get("xp_expr")
        self.active = kwargs.get("active", True)

        self.limited: bool = kwargs.get("limited", False)

    activity_table = sa.Table(
        "activities",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers.id"), nullable=False),
        sa.Column("currency_expr", sa.String(500), nullable=True),
        sa.Column("xp_expr", sa.String(500), nullable=True),
        sa.Column("limited", sa.BOOLEAN, nullable=False, default=False),
        sa.Column("active", sa.Boolean, nullable=False, default=True),
        sa.Index("idx_activity", "guild_id", "name")
    )

    class ActivitySchema(Schema):
        db: AsyncEngine

        id = fields.UUID(required=True)
        guild_id = fields.Integer(required=True)
        name = fields.String(required=True)
        currency_expr = fields.String(required=False, allow_none=True)
        xp_expr = fields.String(required=False, allow_none=True)
        limited = fields.Boolean(required=True)
        active = fields.Boolean(required=True)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db
        @post_load
        def make_activity(self, data, **kwargs) -> "Activity":
            activity = Activity(self.db, **data)

            return activity

    async def upsert(self) -> "Activity":
        update_dict = {
            "currency_expr": self.currency_expr,
            "xp_expr": self.xp_expr,
            "limited": self.limited,
            "active": self.active
        }

        insert_dict = {
            "name": self.name,
            "guild_id": self.guild_id,
            **update_dict
        }

        if hasattr(self, "id") and self.id is not None:
            query = (
                Activity.activity_table.update()
                .where(Activity.activity_table.c.id == self.id)
                .values(**update_dict)
                .returning(Activity.activity_table)
            )
        else:
            query = (
                Activity.activity_table.insert()
                .values(**insert_dict)
                .returning(Activity.activity_table)
            )

        row = await execute_query(self._db, query)

        return Activity.ActivitySchema(self._db).load(dict(row._mapping))
    
    @staticmethod
    async def fetch(db: AsyncEngine, activity_id: Union[uuid.UUID, str], active_only: bool = True) -> "Activity":
        if isinstance(activity_id, str):
            activity_id = uuid.UUID(activity_id)

        query = (
            Activity.activity_table.select()
            .where(Activity.activity_table.c.id == activity_id)
        )

        if active_only:
            query.where(
                Activity.activity_table.c.active == True
            )

        row = await execute_query(db, query)

        if not row:
            return None
        
        activity = Activity.ActivitySchema(db).load(dict(row._mapping))

        return activity
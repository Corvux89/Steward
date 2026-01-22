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
        sa.Column("guild_id", sa.BigInteger, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("currency_expr", sa.String(500), nullable=True),
        sa.Column("xp_expr", sa.String(500), nullable=True),
        sa.Column("limited", sa.BOOLEAN, nullable=False, default=False),
        sa.Column("active", sa.Boolean, nullable=False, default=True),
        sa.PrimaryKeyConstraint("guild_id", "name")
    )

    class ActivitySchema(Schema):
        db: AsyncEngine

        guild_id = fields.Integer(required=True)
        name = fields.String(required=True)
        currency_expr = fields.String(required=True)
        xp_expr = fields.String(required=True)
        limited = fields.Boolean(required=True)
        active = fields.Boolean(required=True)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db
        @post_load
        def make_activity(self, data, **kwargs) -> "Activity":
            activity = Activity(self.db, **data)

            return activity
        
    async def delete(self) -> None:
        query = (
            Activity.activity_table.delete()           
            .where(
                sa.and_(
                    Activity.activity_table.c.name == self.name,
                    Activity.activity_table.c.guild_id == self.guild_id
                )
            )
        )

        await execute_query(self._db, query)

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

        query = (
            insert(Activity.activity_table)
            .values(**insert_dict)
            .returning(Activity.activity_table)
            .on_conflict_do_update(
                index_elements=["guild_id", "name"],
                set_=update_dict
            )
        )

        row = await execute_query(self._db, query)

        return Activity.ActivitySchema(self._db).load(dict(row._mapping))
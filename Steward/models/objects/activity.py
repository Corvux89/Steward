import sqlalchemy as sa

from decimal import Decimal
from marshmallow import Schema, fields, post_load
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncEngine
from Steward.models import metadata
from Steward.utils.dbUtils import execute_query


class Activity:
    def __init__(self, db: AsyncEngine, **kwargs):
        self._db = db

        self.guild_id = kwargs.get("guild_id")
        self.name = kwargs.get("name")

        self.base_currency_value: int = kwargs.get("base_currency_value")
        self.base_xp_value:int = kwargs.get("base_xp_value")
        self.base_currency_ratio: Decimal = kwargs.get("base_currency_ratio")
        self.base_xp_ratio: Decimal = kwargs.get("base_xp_ratio")

        self.limited: bool = kwargs.get("limited", False)

        activity_table = sa.Table(
            "activities",
            metadata,
            sa.Column("guild_id", sa.BigInteger, nullable=False),
            sa.Column("name", sa.String, nullable=False),
            sa.Column("base_currency_value", sa.Integer, nullable=True),
            sa.Column("base_xp_value", sa.Integer, nullable=True),
            sa.Column("base_currency_ratio", sa.DECIMAL, nullable=True),
            sa.Column("base_xp_ratio", sa.DECIMAL, nullable=True),
            sa.Column("limited", sa.BOOLEAN, nullable=False, default=False),
            sa.PrimaryKeyConstraint("guild_id", "name")
        )

        class ActivitySchema(Schema):
            db: AsyncEngine

            guild_id = fields.Integer(required=True)
            name = fields.String(required=True)
            base_currency_value = fields.Integer(required=False, allow_none=True)
            base_xp_value = fields.Integer(required=False, allow_none=True)
            base_currency_ratio = fields.Decimal(required=False, allow_none=True)
            base_xp_ratio = fields.Decimal(required=False, allow_none=True)
            limited = fields.Boolean(required=True, load_default=False)

            def __init__(self, db: AsyncEngine, **kwargs):
                super().__init__(**kwargs)
                self.db = db
            @post_load
            def make_activity(self, data, **kwargs) -> "Activity":
                activity = Activity(self.db, **data)

                return activity
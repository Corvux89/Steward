import sqlalchemy as sa

from decimal import Decimal
from marshmallow import Schema, fields, post_load
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncEngine
from Steward.models import metadata
from Steward.utils.dbUtils import execute_query

# TODO: CRUD operations

class ActivityPoints:
    def __init__(self, db: AsyncEngine, **kwargs):
        self._db = db

        self.guild_id = kwargs.get("guild_id")
        self.level = kwargs.get("level")
        self.points = kwargs.get("points")

    activity_points_table = sa.Table(
        "activity_points",
        metadata,
        sa.Column("guild_id", sa.BigInteger, nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("points", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("guild_id", "level")
    )

    class ActivityPointsSchema(Schema):
        db: AsyncEngine

        guild_id = fields.Integer(required=True)
        level = fields.Integer(required=True)
        points = fields.Integer(required=True)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db

        @post_load
        async def make_activity_points(self, data, **kwargs) -> "ActivityPoints":
            ap = ActivityPoints(self.db, **data)

            return ap
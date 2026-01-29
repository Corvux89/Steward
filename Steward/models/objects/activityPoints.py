import sqlalchemy as sa

from marshmallow import Schema, fields, post_load
from sqlalchemy.dialects.postgresql import insert
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
        self.xp_expr = kwargs.get("xp_expr", "0")
        self.currenct_expr = kwargs.get("currency_expr", "0")

    activity_points_table = sa.Table(
        "activity_points",
        metadata,
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers.id"), nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("points", sa.Integer, nullable=False),
        sa.Column("xp_expr", sa.String(500), nullable=False, default="0"),
        sa.Column("currency_expr", sa.String(500), nullable=False, default="0"),
        sa.PrimaryKeyConstraint("guild_id", "level")
    )

    class ActivityPointsSchema(Schema):
        db: AsyncEngine

        guild_id = fields.Integer(required=True)
        level = fields.Integer(required=True)
        points = fields.Integer(required=True)
        xp_expr = fields.String(required=True)
        currency_expr = fields.String(required=True)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db

        @post_load
        def make_activity_points(self, data, **kwargs) -> "ActivityPoints":
            ap = ActivityPoints(self.db, **data)

            return ap
        
    async def delete(self) -> None:
        query = (
            ActivityPoints.activity_points_table.delete()
            .where(
                sa.and_(
                    ActivityPoints.activity_points_table.c.level == self.level,
                    ActivityPoints.activity_points_table.c.guild_id == self.guild_id
                )
            )
        )

        await execute_query(self._db, query)

    async def upsert(self) -> "ActivityPoints":
        update_dict = {
            "points": self.points,
            "xp_expr": self.xp_expr,
            "currency_expr": self.currenct_expr
        }

        insert_dict = {
            "guild_id": self.guild_id,
            "level": self.level,
            **update_dict
        }

        query = (
            insert(ActivityPoints.activity_points_table)
            .values(**insert_dict)
            .returning(ActivityPoints.activity_points_table)
            .on_conflict_do_update(
                index_elements=["guild_id", "level"],
                set_=update_dict
            )
        )

        row = await execute_query(self._db, query)

        return ActivityPoints.ActivityPointsSchema(self._db).load(dict(row._mapping))
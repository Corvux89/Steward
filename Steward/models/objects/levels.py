import sqlalchemy as sa

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.dialects.postgresql import insert
from marshmallow import Schema, fields, post_load
from Steward.models import metadata
from Steward.models.objects.enum import QueryResultType
from Steward.utils.dbUtils import execute_query

class Levels:
    def __init__(self, db: AsyncEngine, guild_id: int, level: int, xp: int, tier: int):
        self._db = db

        self.guild_id = guild_id
        self.level = level
        self.tier = tier
        self.xp = xp

    level_table = sa.Table(
        "ref_levels",
        metadata,
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers.id"), nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("xp", sa.Integer, nullable=False),
        sa.Column("tier", sa.Integer, nullable=True),
        sa.PrimaryKeyConstraint("guild_id", "level")
    )

    class LevelSchema(Schema):
        db: AsyncEngine

        guild_id = fields.Integer(required=True)
        level = fields.Integer(required=True)
        xp = fields.Integer(required=True)
        tier = fields.Integer(required=False, allow_none=True)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db

        @post_load
        def make_level(self, data, **kwargs):
            level = Levels(self.db, **data)
            return level
        
    async def delete(self) -> None:
        query = (
            Levels.level_table.delete()
            .where(
                sa.and_(
                    Levels.level_table.c.guild_id == self.guild_id,
                    Levels.level_table.c.level == self.level
                )
            )
        )

        await execute_query(self._db, query, QueryResultType.none)

    async def upsert(self) -> "Levels":
        update_dict = {
            "xp": self.xp,
            "tier": self.tier
        }

        insert_dict = {
            "guild_id": self.guild_id,
            "level": self.level,
            **update_dict
        }

        query = (
            insert(Levels.level_table)
            .values(**insert_dict)
            .returning(Levels.level_table)
            .on_conflict_do_update(
                index_elements=["guild_id", "level"],
                set_=update_dict
            )
        )

        row = await execute_query(self._db, query)

        return Levels.LevelSchema(self._db).load(dict(row._mapping))
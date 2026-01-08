from typing import TYPE_CHECKING, List, Union
import discord
import sqlalchemy as sa

from sqlalchemy.ext.asyncio import AsyncEngine
from marshmallow import Schema, fields, post_load
from sqlalchemy.dialects.postgresql import ARRAY
from Steward.models import metadata
from Steward.models.objects.enum import QueryResultType
from Steward.models.objects.npc import NPC
from Steward.utils.dbUtils import execute_query
from constants import BOT_OWNERS

if TYPE_CHECKING:
    from Steward.models.objects.character import Character
    from Steward.models.objects.player import Player
    from Steward.models.objects.currency import CurrencySystem
    from Steward.models.objects.activityPoints import ActivityPoints

class StewardGuild(discord.Guild):
    def __init__(self, db: AsyncEngine, guild: discord.Guild, **kwargs):
        self._db = db
        self.__dict__.update(guild.__dict__)

        self.max_level = kwargs.get("max_level", 3)
        self.currency_limit = kwargs.get("currency_limit", 10)
        self.xp_limit = kwargs.get("xp_limit", 100)
        self.max_characters = kwargs.get("max_characters", 1)
        self.activity_char_count_threshold = kwargs.get("activity_char_count_threshold", 250)
        self.activity_excluded_channels = kwargs.get("activity_excluded_channels", [])

        # Virtual Attributes
        self.npcs: list[NPC] = []
        self.currency: "CurrencySystem" = None
        self.activity_points: list["ActivityPoints"] = []

    guilds_table = sa.Table(
        "guilds",
        metadata,
        sa.Column("id", sa.BigInteger, primary_key=True, nullable=False),
        sa.Column("max_level", sa.Integer, nullable=False, default=3),
        sa.Column("currency_limit", sa.Integer, nullable=False),
        sa.Column("xp_limit", sa.Integer, nullable=False),
        sa.Column("max_characters", sa.Integer, nullable=False),
        sa.Column("activity_char_count_threshold", sa.Integer, nullable=False),
        sa.Column("activity_excluded_channels", ARRAY(sa.BigInteger), nullable=False, default=[])
    )

    class StewardGuildSchema(Schema):
        id = fields.Integer(required=True)
        max_level = fields.Integer()
        currency_limit = fields.Integer()
        xp_limit = fields.Integer()
        max_characters = fields.Integer()
        activity_char_count_threshold = fields.Integer()
        activity_excluded_channels = fields.List(fields.Integer, allow_none=False)

        @post_load
        def make_guild(self, data, **kwargs) -> dict:
            return data

    async def load_currency(self) -> None:
        query = (
            CurrencySystem.currency_table.select()
            .where(CurrencySystem.currency_table.c.guild_id == self.id)
        )

        row = await execute_query(self._db, query)

        if row:
            self.currency = CurrencySystem.CurrencySystemSchema(self._db).load(row)

    async def load_npcs(self) -> None:
            query = (
                NPC.npc_table.select()
                .where(
                    sa.and_(
                        NPC.npc_table.c.guild_id == self.id,
                        NPC.npc_table.c.adventure_id == sa.null()
                    )
                )
                .order_by(NPC.npc_table.c.key.asc())
            )

            rows = await execute_query(self._db, query, QueryResultType.multiple)

            self.npcs = [NPC.NPCSchema(self._db).load(row) for row in rows]

    async def load_acitvity_points(self) -> None:
        query = (
            ActivityPoints.activity_points_table.select()
            .where(ActivityPoints.activity_points_table.c.guild_id == self.id)
            .order_by(ActivityPoints.c.level.asc())
        )

        rows = await execute_query(self._db, query, QueryResultType.multiple)

        self.activity_points = [ActivityPoints.ActivityPointsSchema(self._db).load(row) for row in rows]

    @classmethod
    async def get_or_create(cls, db: AsyncEngine, guild: discord.Guild) -> "StewardGuild":
        query = (
            cls.guilds_table.select()
            .where(cls.guilds_table.c.id == guild.id)
        )

        row = await execute_query(db, query)

        if not row:
            insert_query = (
                cls.guilds_table.insert()
                .values(
                    id=guild.id,
                    max_level=3,
                    currency_limit=10,
                    xp_limit=100,
                    max_characters=1,
                    activity_char_count_threshold=250,
                    activity_excluded_channels=[]
                )
                .returning(cls.guilds_table)
            )

            row = await execute_query(db, insert_query)

        data = cls.StewardGuildSchema().load(row)

        stewardGuild = cls(db, guild, **data)
        await stewardGuild.load_currency()
        await stewardGuild.load_npcs()
        await stewardGuild.load_acitvity_points()
        
        return stewardGuild
    
    async def save(self) -> None:
        query = (
            self.guilds_table.update()
            .where(self.guilds_table.c.id == self.id)
            .values(
                max_level = self.max_level,
                currency_limit = self.currency_limit,
                xp_limit = self.xp_limit,
                max_characters = self.max_characters,
                activity_char_count_threshold = self.activity_char_count_threshold,
                activity_excluded_channels = self.activity_excluded_channels
            )
            .returning(self.guilds_table)
        )

        await execute_query(self._db, query)

    async def get_npc(self, **kwargs) -> NPC:
        if kwargs.get("key"):
            return next(
                (npc for npc in self.npcs if npc.key == kwargs.get("key")),None
            )
        
        elif kwargs.get("name"):
            return next(
                (
                    npc for npc in self.npcs
                    if npc.name.lower() == kwargs.get("name").lower()
                ),None
            )
        
        return None
    
    def is_admin(self, member: Union[discord.Member, "Player"]):
        if member.id in BOT_OWNERS:
            return True
        
        elif member.guild_permissions.administrator:
            return True
        
        return False
    
    async def get_all_characters(self) -> List["Character"]:
        from Steward.models.objects.character import Character

        query = (
            Character.characters_table.select()
            .where(
                sa.and_(
                    Character.characters_table.c.active == True,
                    Character.characters_table.c.guild_id == self.id
                )
            )
            .order_by(Character.characters_table.c.name.desc())
        )

        rows = await execute_query(self._db, query, QueryResultType.multiple)

        characters = [await Character.CharacterSchema(self._db).load(row) for row in rows]

        return characters


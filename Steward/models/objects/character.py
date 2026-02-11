from typing import TYPE_CHECKING, Union
import sqlalchemy as sa
import uuid

from marshmallow import Schema, fields, post_load
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncEngine

from Steward.models.objects.enum import LogEvent

from ...models import metadata
from ...utils.dbUtils import execute_query

if TYPE_CHECKING:
    from .player import Player
    from ...bot import StewardApplicationContext
    

class Character:
    def __init__(self, db: AsyncEngine, **kwargs):
        self._db = db

        self.id = kwargs.get("id")
        self.name = kwargs.get("name")
        self.level: int = kwargs.get("level", 1)
        self.species_str = kwargs.get("species_str", "")
        self.class_str = kwargs.get("class_str", "")
        self.guild_id = kwargs.get("guild_id")
        self.player_id = kwargs.get("player_id")
        self.active: bool = kwargs.get("active", True)
        self.primary_character: bool = kwargs.get("primary_character", False)
        self.channels: list = kwargs.get("channels", [])
        self.avatar_url = kwargs.get("avatar_url", "")
        self.nickname = kwargs.get("nickname", "")
        self.currency = kwargs.get("currency", 0)
        self.activity_points = kwargs.get("activity_points", 0)
        self.xp = kwargs.get("xp", 0)
        self.limited_xp = kwargs.get("limited_xp", 0)
        self.limited_currency = kwargs.get("limited_currency", 0)

    characters_table = sa.Table(
        "characters",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("species_str", sa.String, nullable=True),
        sa.Column("class_str", sa.String, nullable=True),
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers.id"), nullable=False),
        sa.Column("player_id", sa.BigInteger, nullable=False),
        sa.Column("active", sa.BOOLEAN, nullable=False, default=True),
        sa.Column("primary_character", sa.BOOLEAN, nullable=False, default=True),
        sa.Column("channels", ARRAY(sa.BigInteger), nullable=False, default=[]),
        sa.Column("avatar_url", sa.String, nullable=True),
        sa.Column("nickname", sa.String, nullable=True),
        sa.Column("currency", sa.DECIMAL, nullable=False),
        sa.Column("activity_points", sa.Integer, nullable=False, default=0),
        sa.Column("xp", sa.Integer, nullable=False, default=0),
        sa.Column("limited_xp", sa.Integer, nullable=False, default=0),
        sa.Column("limited_currency", sa.Integer, nullable=False, default=0),
        sa.Index("idx_guild_player", "guild_id", "player_id")
    )

    class CharacterSchema(Schema):
        db: AsyncEngine
        
        id = fields.UUID(required=True)
        name = fields.String(required=True)
        level = fields.Integer(required=True)   
        species_str = fields.String(allow_none=True)
        class_str = fields.String(allow_none=True)
        guild_id = fields.Integer(required=True)
        player_id = fields.Integer(required=True)
        active = fields.Boolean(required=True)
        primary_character = fields.Boolean(required=True)
        channels = fields.List(fields.Integer, allow_none=False)
        avatar_url = fields.String(allow_none=True)
        nickname = fields.String(allow_none=True)
        currency = fields.Decimal(required=True, allow_none=False)
        activity_points = fields.Integer(required=True)
        xp = fields.Integer(required=True)
        limited_xp = fields.Integer(required=True)
        limited_currency = fields.Integer(required=True)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db

        @post_load
        def make_character(self, data, **kwargs) -> "Character":
            character = Character(self.db, **data)

            return character
    
    @staticmethod
    async def fetch(db: AsyncEngine, char_id: Union[uuid.UUID, str], active_only: bool = True) -> "Character":
        if isinstance(char_id, str):
            char_id = uuid.UUID(char_id)

        query = (
            Character.characters_table.select()
            .where(Character.characters_table.c.id == char_id)
        )

        if active_only:
            query.where(
                Character.characters_table.c.active == True
            )

        row = await execute_query(db, query)

        if not row:
            return None
        
        character: Character = Character.CharacterSchema(db).load(dict(row._mapping))

        return character
        


    async def upsert(self) -> "Character":
        update_dict = {
            "name": self.name,
            "level": self.level,
            "species_str": self.species_str,
            "class_str": self.class_str,
            "active": self.active,
            "primary_character": self.primary_character,
            "channels": self.channels,
            "nickname": self.nickname,
            "activity_points": self.activity_points,
            "xp": self.xp,
            "currency": self.currency,
            "limited_xp": self.limited_xp,
            "limited_currency": self.limited_currency,
            "avatar_url": self.avatar_url
        }

        insert_dict = {
            "guild_id": self.guild_id,
            "player_id": self.player_id,
            **update_dict
            }

        if hasattr(self, "id") and self.id is not None:
            query = (
                Character.characters_table.update()
                .where(Character.characters_table.c.id == self.id)
                .values(**update_dict)
                .returning(Character.characters_table)
            )
        else:
            query = (
                Character.characters_table.insert()
                .values(**insert_dict)
                .returning(Character.characters_table)
            )
        row = await execute_query(self._db, query)
        character: Character = Character.CharacterSchema(self._db).load(dict(row._mapping))

        return character  
    
    @property
    def mention(self):          
        return self.nickname if self.nickname else self.name

    async def update_activity_points(
            self,
            ctx: "StewardApplicationContext",
            increment: bool = True
    ) -> None:
        from .player import Player

        player = await Player.get_or_create(ctx.bot.db, ctx.server.get_member(self.player_id))
        modifier = 1 if increment else -1
        old_point = ctx.server.get_activitypoint_for_points(self.activity_points)
        
        self.activity_points += 1 * modifier
        new_point = ctx.server.get_activitypoint_for_points(self.activity_points)

        if (not old_point and new_point) or old_point.level != new_point.level:
            from .log import StewardLog

            activity_log = await StewardLog.create(
                ctx.bot,
                ctx.bot.user,
                player,
                LogEvent.reward,
                character=self,
                notes=f"Activity level {new_point.level}{' [REVERSION]' if old_point and new_point.level < old_point.level else ''}",
                currency=new_point.currenct_expr,
                xp=new_point.xp_expr
            )

            ctx.bot.dispatch(LogEvent.reward.name, log=activity_log)
        else:
            await self.upsert()





            
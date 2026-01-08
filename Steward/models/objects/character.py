from decimal import Decimal
import sqlalchemy as sa
import uuid

from marshmallow import Schema, fields, post_load
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncEngine
from Steward.models import metadata
from Steward.utils.dbUtils import execute_query

class Character:
    def __init__(self, db: AsyncEngine, **kwargs):
        self._db = db

        self.id = kwargs.get("id")
        self.name = kwargs.get("name")
        self.level: int = kwargs.get("level", 3)
        self.species_str = kwargs.get("species_str")
        self.class_str = kwargs.get("class_str")
        self.guild_id = kwargs.get("guild_id")
        self.player_id = kwargs.get("player_id")
        self.active: bool = kwargs.get("active", True)
        self.primary_character: bool = kwargs.get("primary_character", False)
        self.channels: list = kwargs.get("channels", [])
        self.avatar_url = kwargs.get("avatar_url")
        self.nickname = kwargs.get("nickname")
        self.coinpurse: dict[str, Decimal] = kwargs.get("coinpurse", {})

    characters_table = sa.Table(
        "characters",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4()),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("species_str", sa.String, nullable=True),
        sa.Column("class_str", sa.String, nullable=True),
        sa.Column("guild_id", sa.BigInteger, nullable=False),
        sa.Column("player_id", sa.BigInteger, nullable=False),
        sa.Column("active", sa.BOOLEAN, nullable=False, default=True),
        sa.Column("primary_character", sa.BOOLEAN, nullable=False, default=True),
        sa.Column("channels", ARRAY(sa.BigInteger), nullable=False, default=[]),
        sa.Column("avatar_url", sa.String, nullable=True),
        sa.Column("nickname", sa.String, nullable=True),
        sa.Column("coinpurse", sa.JSON, nullable=False),
        sa.Index("idx_guild_player", "guild_id", "player_id")
    )

    class CharacterSchema(Schema):
        db: AsyncEngine
        
        id = fields.Integer(required=True)
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
        coinpurse = fields.Dict(required=False, load_default=dict)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db

        @post_load
        async def make_character(self, data, **kwargs) -> "Character":
            Character = Character(self.db, **data)

            return Character

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
            "coinpurse": self.coinpurse
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
        character: Character = await Character.CharacterSchema(self._db).load(row)

        return character  
    
    @property
    def mention(self):          
        return self.nickname if self.nickname else self.name
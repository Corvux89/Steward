from typing import TYPE_CHECKING
import discord
import uuid
import sqlalchemy as sa

from datetime import datetime, timezone
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.dialects.postgresql import ARRAY, insert
from marshmallow import Schema, fields, post_load
from Steward.models import metadata
from Steward.models.objects.enum import QueryResultType, WebhookType
from Steward.utils.dbUtils import execute_query
from Steward.utils.discordUtils import dm_check, get_webhook

if TYPE_CHECKING:
    from Steward.bot import StewardBot
    from .player import Player
    from .character import Character


class Patrol:
    def __init__(self, db: AsyncEngine, channel: discord.TextChannel, host: "Player", **kwargs):
        self._db = db
        self.channel = channel
        self.host = host

        self.id = kwargs.get('id')
        self.notes = kwargs.get('notes')
        self.end_ts = kwargs.get('end_ts')
        self.created_ts = kwargs.get('created_ts', datetime.now(timezone.utc))
        self.outcome = kwargs.get('outcome')
        self.pinned_message_id = kwargs.get('pinned_message_id')

        self.characters: list["Character"] = kwargs.get('characters', [])
        self.character_ids = kwargs.get('character_ids')

    patrol_table = sa.Table(
        "patrols",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers.id"), nullable=False),
        sa.Column("channel_id", sa.BigInteger, nullable=False),
        sa.Column("host_id", sa.BigInteger, nullable=False),
        sa.Column("created_ts", sa.TIMESTAMP(timezone=timezone.utc), nullable=False),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("character_ids", sa.ARRAY(sa.UUID), nullable=False, default=[]),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("pinned_message_id", sa.BigInteger, nullable=True),
        sa.Column("end_ts", sa.TIMESTAMP(timezone=timezone.utc), nullable=True),
    )

    class PatrolSchema(Schema):
        id = fields.UUID(required=True)
        guild_id = fields.Integer(required=True)
        channel_id = fields.Integer(required=True)
        host_id = fields.Integer(required=True)
        created_ts = fields.DateTime("timestamp", required=True)
        outcome = fields.String(allow_none=True)
        character_ids = fields.List(fields.UUID(), load_default=[])
        notes = fields.String(allow_none=True)
        pinned_message_id = fields.Integer()
        end_ts = fields.DateTime("timestamp", allow_none=True)

        @post_load
        def make_patrol(self, data, **kwargs) -> dict:
            return data


    async def upsert(self) -> "Patrol":
        update_dict = {
            "notes": self.notes,
            "end_ts": self.end_ts,
            "character_ids": [c.id for c in self.characters],
            "pinned_message_id": self.pinned_message_id,
            "outcome": self.outcome
        }

        insert_dict = {
            "channel_id": self.channel.id,
            "guild_id": self.channel.guild.id,
            "host_id": self.host.id,
            "created_ts": self.created_ts,
            **update_dict
        }

        if hasattr(self, "id") and self.id is not None:
            query = (
                self.patrol_table.update()
                .where(self.patrol_table.c.id == self.id)
                .values(**update_dict)
                .returning(self.patrol_table)
            )
        else:
            query = (
                self.patrol_table.insert()
                .values(**insert_dict)
                .returning(self.patrol_table)
            )

        result = await execute_query(self._db, query)

        if self.id is None and result:
            row = result[0] if isinstance(result, list) else result
            self.id = dict(row._mapping)["id"]

        return self
    
    async def load_characters(self) -> None:
        from .character import Character

        if not hasattr(self, "character_ids"):
            return
        
        for char_id in getattr(self, "character_ids", []):
            character = await Character.fetch(self._db, char_id)

            if character:
                self.characters.append(character)      

    
    @classmethod
    async def fetch(cls, bot: "StewardBot", channel: discord.TextChannel, message_id: int = None) -> "Patrol":
        from .player import Player

        query = (
            cls.patrol_table.select()
            .where(
                sa.and_(
                    cls.patrol_table.c.channel_id == channel.id,
                    cls.patrol_table.c.end_ts == sa.null()
                )
            )
        )

        if message_id:
            query = query.where(
                cls.patrol_table.c.pinned_message_id == message_id
            )

        row = await execute_query(bot.db, query)

        if not row:
            return None
        
        data = cls.PatrolSchema().load(dict(row._mapping))
        host_member = channel.guild.get_member(data["host_id"])
        host = await Player.get_or_create(bot.db, host_member)
        patrol = cls(bot.db, channel, host, **data)
        await patrol.load_characters()

        return patrol
    
    @classmethod
    async def fetch_all(cls, bot: "StewardBot") -> list["Patrol"]:
        query = (
            cls.patrol_table.select()
            .where(
                cls.patrol_table.c.end_ts == sa.null()
            )
        )

        rows = await execute_query(bot.db, query, QueryResultType.multiple)

        if not rows:
            return []
        
        if not isinstance(rows, list):
            rows = [rows]

        patrols = []

        for row in rows:
            patrol_data = dict(row._mapping)
            guild = bot.get_guild(patrol_data["guild_id"])
            host = guild.get_member(patrol_data["host_id"])
            channel = guild.get_channel_or_thread(patrol_data["channel_id"])
            patrol = cls(bot.db, channel, host, **patrol_data)

            await patrol.load_characters()

            patrols.append(patrol)

        return patrols
    
    async def refresh_view(self, bot: "StewardBot") -> None:
        from ..views.patrol import PatrolView
        if not self.pinned_message_id:
            return 
        
        view = PatrolView(bot, self)
        message = await self.channel.fetch_message(self.pinned_message_id)

        if message:
            await message.edit(view=view)


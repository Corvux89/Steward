from datetime import datetime, timezone
from typing import TYPE_CHECKING, Union
import uuid
import sqlalchemy as sa

from sqlalchemy.dialects.postgresql import insert
from marshmallow import Schema, fields, post_load
from Steward.models import metadata
from Steward.models.objects.enum import QueryResultType
from Steward.utils.dbUtils import execute_query


if TYPE_CHECKING:
    from .character import Character
    from .player import Player
    from .servers import Server
    from ...bot import StewardBot

class Request:
    def __init__(
            self, 
            bot: "StewardBot",
            **kwargs
        ):
        self._bot = bot

        self.id = kwargs.get('id')
        
        self.guild_id = kwargs.get('guild_id')
        self.channel_id = kwargs.get('channel_id')
        self.player_id = kwargs.get('player_id')

        self.message_id = kwargs.get('message_id')

        self.player_characters: dict["Player", list["Character"]] = kwargs.get('player_characters', {})
        self.notes = kwargs.get('notes', '')

        self.button_captions: [] = kwargs.get('button_captions', [])

        self.created_ts: datetime = kwargs.get("created_ts", datetime.now(timezone.utc))

    async def server(self) -> "Server":
        from .servers import Server
        return await Server.get_or_create(self._bot.db, self._bot.get_guild(self.guild_id))
    
    @property
    def channel(self):
        return self._bot.get_channel(self.channel_id)
    
    async def player(self) -> "Player":
        from .player import Player
        server = await self.server()
        return await Player.get_or_create(self._bot.db, server.get_member(self.player_id))
    
    @property
    def epoch_time(self) -> int:
        return int(self.created_ts.timestamp())  

    request_table = sa.Table(
        "ref_requests",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers.id") ,nullable=False),
        sa.Column("channel_id", sa.BigInteger, nullable=False),
        sa.Column("player_id", sa.BigInteger, nullable=False),
        sa.Column("notes", sa.String, nullable=True),
        sa.Column("button_captions", sa.ARRAY(sa.String), nullable=False, default=[]),
        sa.Column("message_id", sa.BigInteger, nullable=True),
        sa.Column("created_ts", sa.TIMESTAMP(timezone=timezone.utc), nullable=False),
    )

    class RequestSchema(Schema):
        id = fields.UUID(required=True)
        guild_id = fields.Integer()
        channel_id = fields.Integer()
        player_id = fields.Integer()
        notes = fields.String(allow_none=True)
        button_captions = fields.List(fields.String)
        message_id = fields.Integer(allow_none=True)
        created_ts = fields.DateTime("timestamp")

        @post_load
        def make_request(self, data, **kwargs) -> dict:
            return data
        
    request_characters_table = sa.Table(
        "ref_request_characters",
        metadata,
        sa.Column("request_id", sa.UUID, sa.ForeignKey("ref_requests.id"), primary_key=True),
        sa.Column("player_id", sa.BigInteger, primary_key=True),
        sa.Column("character_id", sa.UUID, sa.ForeignKey("characters.id"), primary_key=True)
    )

    class RequestCharacters(Schema):
        request_id = fields.UUID(required=True)
        player_id = fields.Integer(required=True)
        character_id = fields.Integer(required=True)

        @post_load
        def make_characters(self, data, **kwargs) -> dict:
            return data
        
    async def upsert(self) -> "Request":
        update_dict = {
            "notes": self.notes,
            "button_captions": self.button_captions,
            "message_id": self.message_id
        }

        insert_dict = {
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "player_id": self.player_id,
            "created_ts": datetime.now(timezone.utc),
            **update_dict
        }

        if hasattr(self, "id") and self.id is not None:
            query = (
                self.request_table.update()
                .values(**update_dict)
                .returning(self.request_table)
            )
        else:
            query = (
                self.request_table.insert()
                .values(**insert_dict)
                .returning(self.request_table)
            )

        result = await execute_query(self._bot.db, query)

        if self.id is None and result:
            row = result[0] if isinstance(result, list) else result
            self.id = dict(row._mapping)["id"]

        # Sync player characters
        # TODO: WHY THIS NO WORK
        current_pairs: set[tuple[int, uuid.UUID]] = set()

        for player, characters in self.player_characters.items():
            for character in characters:
                current_pairs.add((player.id, character.id))

        if current_pairs:
            delete_query= (
                self.request_characters_table.delete()
                .where(
                    sa.and_(
                        self.request_characters_table.c.request_id == self.id,
                        sa.not_(
                            sa.tuple_(
                                self.request_characters_table.c.player_id,
                                self.request_characters_table.c.character_id
                            ).in_(current_pairs)
                        )
                    )
                )
            )
            await execute_query(self._bot.db, delete_query, QueryResultType.none)

            for player_id, character_id in current_pairs:
                insert_dict = {
                    "request_id": self.id,
                    "player_id": player_id,
                    "character_id": character_id
                }

                character_query = (
                    insert(self.request_characters_table)
                    .values(insert_dict)
                    .on_conflict_do_nothing()
                )

                await execute_query(self._bot.db, character_query, QueryResultType.none)

        else:
            delete_all_query = (
                self.request_characters_table.delete()
                .where(self.request_characters_table.c.request_id == self.id)
            )
            await execute_query(self._bot.db, delete_all_query)

        return self
    
    async def delete(self) -> None:
        delete_characters_query = (
            self.request_characters_table.delete()
            .where(
                self.request_characters_table.c.request_id == self.id
            )
        )

        await execute_query(self._bot.db, delete_characters_query)

        query = (
            self.request_table.delete()
            .where(self.request_table.c.id == self.id)
        )

        await execute_query(self._bot.db, query)

    @classmethod
    async def fetch(cls, bot: "StewardBot", message_id: int) -> "Request":

        query = (
            cls.request_table.select()
            .where(cls.request_table.c.message_id == message_id)
        )

        row = await execute_query(bot.db, query)

        if not row:
            return None
        
        request_data = dict(row._mapping)
        request = cls(bot, **request_data)

        character_query = (
            cls.request_characters_table.select()
            .where(cls.request_characters_table.c.request_id == request.id)
        )

        char_rows = await execute_query(bot.db, character_query, QueryResultType.multiple)

        if not char_rows:
            request.player_characters = {}
            return request
        
        if not isinstance(char_rows, list):
            char_rows = [char_rows]

        from .player import Player
        from .character import Character

        server = await request.server()
        player_cache: dict[int, "Player"] = {}
        player_characters: dict["Player", list["Character"]] = {}

        for row in char_rows:
            mapping = row._mapping
            player_id = mapping['player_id']
            character_id = mapping['character_id']

            if player_id not in player_cache:
                player_cache[player_id] = await Player.get_or_create(
                    bot.db,
                    server.get_member(player_id)
                )

            player = player_cache[player_id]
            character = await Character.fetch(bot.db, character_id, active_only=False)
            if character is None:
                continue

            if player not in player_characters:
                player_characters[player] = []
            player_characters[player].append(character)

        request.player_characters = player_characters
        return request



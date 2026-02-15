from datetime import datetime, timezone
from typing import TYPE_CHECKING, Union
import uuid
import sqlalchemy as sa
import discord

from sqlalchemy.dialects.postgresql import insert
from marshmallow import Schema, fields, post_load
from Steward.models import metadata
from Steward.models.objects.enum import QueryResultType
from Steward.utils.dbUtils import execute_query
from Steward.utils.discordUtils import try_delete
from constants import CHANNEL_BREAK


if TYPE_CHECKING:
    from .character import Character
    from .player import Player
    from .servers import Server
    from ...bot import StewardBot
    from .activity import Activity

class Request:
    def __init__(
            self, 
            bot: "StewardBot",
            **kwargs
        ):
        self._bot = bot

        self.id = kwargs.get('id')
        
        self.guild_id = kwargs.get('guild_id')
        self.player_id = kwargs.get('player_id')

        self.player_channel_id = kwargs.get('player_channel_id')
        self.player_message_id = kwargs.get('player_message_id')
        
        self.staff_channel_id = kwargs.get('staff_channel_id')
        self.staff_message_id = kwargs.get('staff_message_id')

        

        self.player_characters: dict["Player", list["Character"]] = kwargs.get('player_characters', {})
        self.notes = kwargs.get('notes', '')
        self.player_message: discord.Message = kwargs.get('player_message')
        self.staff_message: discord.Message = kwargs.get('staff_message')
        self.server: "Server" = kwargs.get('server')

        self.created_ts: datetime = kwargs.get("created_ts", datetime.now(timezone.utc))
    
    @property
    def player_channel(self):
        return self._bot.get_channel(self.player_channel_id)
    
    @property
    def staff_channel(self):
        return self._bot.get_channel(self.staff_channel_id)
    
    @property
    def primary_player(self) -> "Player":
        return next(
            (p for p in self.player_characters.keys() if p.id == self.player_id),
            None
        )
    
    @property
    def primary_character(self) -> "Character":
        for player, characters in self.player_characters.items():
            if player.id == self.player_id:
                return characters[0]
    
    @property
    def epoch_time(self) -> int:
        return int(self.created_ts.timestamp())  

    request_table = sa.Table(
        "ref_requests",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers.id") ,nullable=False),
        sa.Column("player_channel_id", sa.BigInteger, nullable=False),
        sa.Column("staff_channel_id", sa.BigInteger, nullable=True),
        sa.Column("player_id", sa.BigInteger, nullable=False),
        sa.Column("notes", sa.String, nullable=True),
        sa.Column("staff_message_id", sa.BigInteger, nullable=True),
        sa.Column("player_message_id", sa.BigInteger, nullable=True),
        sa.Column("created_ts", sa.TIMESTAMP(timezone=timezone.utc), nullable=False),
    )

    class RequestSchema(Schema):
        id = fields.UUID(required=True)
        guild_id = fields.Integer()
        player_channel_id = fields.Integer()
        staff_channel_id = fields.Integer(allow_none=True)
        player_id = fields.Integer()
        notes = fields.String(allow_none=True)
        staff_message_id = fields.Integer(allow_none=True)
        player_message_id = fields.Integer(allow_none=True)
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
            "staff_message_id": self.staff_message_id,
            "staff_channel_id": self.staff_channel_id,
            "player_message_id": self.player_message_id
        }

        insert_dict = {
            "guild_id": self.guild_id,
            "player_channel_id": self.player_channel_id,
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
        delete_all_query = (
            self.request_characters_table.delete()
            .where(self.request_characters_table.c.request_id == self.id)
        )
        await execute_query(self._bot.db, delete_all_query, QueryResultType.none)  
        
        for player, characters in self.player_characters.items():
            for character in characters:
                insert_dict = {
                    "request_id": self.id,
                    "player_id": player.id,
                    "character_id": character.id
                }

                character_query = (
                    self.request_characters_table.insert()
                    .values(**insert_dict)
                )

                result = await execute_query(self._bot.db, character_query, QueryResultType.none)

        return self
    
    async def delete(self) -> None:
        if self.staff_message:
            await try_delete(self.staff_message)

        if self.player_message:
            await try_delete(self.player_message)

        delete_characters_query = (
            self.request_characters_table.delete()
            .where(
                self.request_characters_table.c.request_id == self.id
            )
        )

        await execute_query(self._bot.db, delete_characters_query, QueryResultType.none)

        query = (
            self.request_table.delete()
            .where(self.request_table.c.id == self.id)
        )

        await execute_query(self._bot.db, query, QueryResultType.none)

    @classmethod
    async def fetch_all(cls, bot: "StewardBot", guild_id: int = None, player_id: int = None) -> list["Request"]:
        """
        Fetch all requests, optionally filtered by guild_id and/or player_id.
        
        Args:
            bot: The StewardBot instance
            guild_id: Optional guild ID to filter by
            player_id: Optional player ID to filter by
            
        Returns:
            List of Request objects
        """
        from .servers import Server

        conditions = []
        if guild_id is not None:
            conditions.append(cls.request_table.c.guild_id == guild_id)
        if player_id is not None:
            conditions.append(cls.request_table.c.player_id == player_id)

        query = cls.request_table.select()
        if conditions:
            query = query.where(sa.and_(*conditions))

        rows = await execute_query(bot.db, query, QueryResultType.multiple)

        if not rows:
            return []

        if not isinstance(rows, list):
            rows = [rows]

        requests = []
        for row in rows:
            request_data = dict(row._mapping)
            request = cls(bot, **request_data)

            character_query = (
                cls.request_characters_table.select()
                .where(cls.request_characters_table.c.request_id == request.id)
            )

            char_rows = await execute_query(bot.db, character_query, QueryResultType.multiple)

            if not char_rows:
                request.player_characters = {}
            else:
                if not isinstance(char_rows, list):
                    char_rows = [char_rows]

                from .player import Player
                from .character import Character

                request.server = await Server.get_or_create(bot.db, bot.get_guild(request.guild_id))
                player_cache: dict[int, "Player"] = {}
                player_characters: dict["Player", list["Character"]] = {}

                for char_row in char_rows:
                    mapping = char_row._mapping
                    player_id_char = mapping['player_id']
                    character_id = mapping['character_id']

                    if player_id_char not in player_cache:
                        player_cache[player_id_char] = await Player.get_or_create(
                            bot.db,
                            request.server.get_member(player_id_char)
                        )

                    player = player_cache[player_id_char]
                    character = await Character.fetch(bot.db, character_id, active_only=False)
                    if character is None:
                        continue

                    if player not in player_characters:
                        player_characters[player] = []
                    player_characters[player].append(character)

                request.player_characters = player_characters

            try:
                if request.staff_message_id:
                    request.staff_message = await request.staff_channel.fetch_message(request.staff_message_id)
                
                if request.player_message_id:
                    request.player_message = await request.player_channel.fetch_message(request.player_message_id)
            except:
                pass

            requests.append(request)

        return requests

    @classmethod
    async def fetch(cls, bot: "StewardBot", message_id: int) -> "Request":
        from .servers import Server

        query = (
            cls.request_table.select()
            .where(
                sa.or_(
                    cls.request_table.c.staff_message_id == message_id,
                    cls.request_table.c.player_message_id == message_id
                )
            )
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

        request.server = await Server.get_or_create(bot.db, bot.get_guild(request.guild_id))
        player_cache: dict[int, "Player"] = {}
        player_characters: dict["Player", list["Character"]] = {}

        for row in char_rows:
            mapping = row._mapping
            player_id = mapping['player_id']
            character_id = mapping['character_id']

            if player_id not in player_cache:
                player_cache[player_id] = await Player.get_or_create(
                    bot.db,
                    request.server.get_member(player_id)
                )

            player = player_cache[player_id]
            character = await Character.fetch(bot.db, character_id, active_only=False)
            if character is None:
                continue

            if player not in player_characters:
                player_characters[player] = []
            player_characters[player].append(character)

        request.player_characters = player_characters

        try:
            if request.staff_message_id:
                request.staff_message = await request.staff_channel.fetch_message(request.staff_message_id)
            
            if request.player_message_id:
                request.player_message = await request.player_channel.fetch_message(request.player_message_id)
        except:
            pass

        return request
    
    async def approve(self, bot: "StewardBot", activity: "Activity", author: Union[discord.User, "Player"]):
        from .log import StewardLog
        from .enum import LogEvent
        from ..views.request import LoggedView

        for player, characters in self.player_characters.items():
            for character in characters:
                await StewardLog.create(
                        bot,
                        author,
                        player,
                        LogEvent.activity,
                        character=character,
                        activity=activity,
                        notes=self.notes
                    )
        try:
            view = LoggedView(self, activity, author)
            await self.player_channel.send(view=view)
            await self.player_channel.send(CHANNEL_BREAK)
        except:
            pass
        
        await self.delete()



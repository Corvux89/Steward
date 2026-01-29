from typing import TYPE_CHECKING, Union
import discord
import sqlalchemy as sa

from sqlalchemy.ext.asyncio import AsyncEngine
from marshmallow import Schema, fields, post_load
from Steward.models import metadata

from Steward.models.objects.enum import QueryResultType
from Steward.utils.dbUtils import execute_query
from Steward.utils.discordUtils import get_webhook

if TYPE_CHECKING:
    from Steward.models.objects.activityPoints import ActivityPoints
    from Steward.models.objects.character import Character
    from Steward.bot import StewardContext
    from Steward.models.objects.npc import NPC

class Player(discord.Member):
    def __init__(self, db: AsyncEngine, member: discord.Member, **kwargs):
        self._db = db

        for attr in member.__slots__:
            try:
                setattr(self, attr, getattr(member, attr))
            except AttributeError:
                pass

        self.statistics: dict[str, int]  = kwargs.get("statistics", {})
        self.campaign = kwargs.get("campaign")
        self.notes = kwargs.get("notes")
        self.staff_points = kwargs.get("staff_points", 0)

        # Calculated Attributes
        self.characters: list["Character"] = []

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id} guild={self.guild.id} name={self.display_name!r}>"

    player_table = sa.Table(
        "players",
        metadata,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers.id") ,primary_key=True),
        sa.Column("statistics", sa.JSON, nullable=False),
        sa.Column("campaign", sa.String, nullable=True),
        sa.Column("notes", sa.String, nullable=True),
        sa.Column("staff_points", sa.Integer, nullable=False, default=0)
    )

    class PlayerSchema(Schema):
        id = fields.Integer(required=True)
        guild_id = fields.Integer(required=True)
        statistics = fields.Dict(required=False, load_default=dict)
        campaign = fields.String(allow_none=True)
        notes = fields.String(allow_none=True)
        staff_points = fields.Integer(allow_none=False, load_default=0)

        @post_load
        def make_player(self, data, **kwargs) -> dict:
            return data

    async def load_characters(self) -> None:
        from Steward.models.objects.character import Character

        query = (
            Character.characters_table.select()
            .where(
                sa.and_(
                    Character.characters_table.c.player_id == self.id,
                    Character.characters_table.c.guild_id == self.guild.id
                )
            )
        )

        rows = await execute_query(self._db, query, QueryResultType.multiple)

        self.characters = [Character.CharacterSchema(self._db).load(dict(row._mapping)) for row in rows]

    @property
    def active_characters(self) -> list["Character"]:
        return [c for c in self.characters if c.active]
    
    @property
    def highest_level_character(self) -> "Character":
        character = None
        for char in self.active_characters:
            if character is None:
                character = char
            elif character and char.level > character.level:
                character = char

        return character
    
    @property
    def discord_url(self) -> str:
        return f"https://discrodapp.com/users/{self.id}"
    
    @property
    def primary_character(self) -> "Character":
        for char in self.active_characters:
            if char.primary_character:
                return char
            
        return self.active_characters[0]
    
    def get_channel_character(self, channel: discord.abc.Messageable) -> "Character":
        for char in self.active_characters:
            if channel.id in char.channels:
                return char
            
    async def get_webhook_character(self, channel: discord.abc.Messageable) -> "Character":
        if character := self.get_channel_character(channel):
            return character
        elif character := self.primary_character:
            return character

    async def send_webhook_message(self, ctx: "StewardContext", character: "Character", content: str) -> None:
        webhook = await get_webhook(ctx.channel)

        kwargs = {
            "username": f"[{character.level}] {character.name} // {self.display_name}",
            "avatar_url": character.avatar_url if character.avatar_url else self.display_avatar.url if self.display_avatar else None,
            "content": content
        }
        
        if isinstance(ctx.channel, discord.Thread):
            kwargs["thread"] = ctx.channel

        await webhook.send(**kwargs)

    async def edit_webhook_message(self, ctx: "StewardContext", message_id: int, content: str) -> None:
        webhook = await get_webhook(ctx.channel)

        kwargs = {
            "content": content
        }

        if isinstance(ctx.channel, discord.Thread):
            kwargs["thread"] = ctx.channel

        await webhook.edit_message(message_id, **kwargs)
    
    @classmethod
    async def get_or_create(cls, db: AsyncEngine, member: discord.Member) -> "Player":
        query = (
            cls.player_table.select()
            .where(sa.and_(
                cls.player_table.c.id == member.id, 
                cls.player_table.c.guild_id == member.guild.id))
        )

        row = await execute_query(db, query)

        if not row:
            insert_query = (
                cls.player_table.insert()
                .values(
                    id=member.id,
                    guild_id=member.guild.id,
                    statistics={}
                )
                .returning(cls.player_table)
            )
            row = await execute_query(db, insert_query)

        data = cls.PlayerSchema().load(dict(row._mapping))
        
        player = cls(db, member, **data)
        await player.load_characters()
        return player

    
    async def save(self) -> None:
        query = (
            self.player_table.update()
            .where(sa.and_(
                self.player_table.c.id == self.id,
                self.player_table.c.guild_id == self.guild.id
            ))
            .values(
                {
                    "statistics": self.statistics,
                    "campaign": getattr(self, "campaign"),
                    "notes": getattr(self, "notes"),
                    "staff_points": getattr(self, "staff_points")
                }                                
            )
            .returning(self.player_table)
        )

        await execute_query(self._db, query)

    async def update_command_count(self, command: str) -> None:
        self.statistics.setdefault("commands", {}).setdefault(command, 0)

        self.statistics["commands"][command] += 1

        await self.save()

    async def update_post_stats(self, character: Union["Character", "NPC"], post: discord.Message, **kwargs) -> None:
        from .character import Character
        
        content: str = kwargs.get("content", post.content)
        retract: bool = kwargs.get("retract", False)

        current_date = post.created_at.strftime("%Y-%m-%d")

        # Determine key and id
        if isinstance(character, Character):
            key = "character"
            id = str(character.id)
        else:
            key = "npc"
            id = character.key

        self.statistics.setdefault(key, {}).setdefault(id, {}).setdefault(
            current_date,
            {"num_lines": 0, "num_words": 0, "num_characters": 0, "count": 0}
        )

        daily_stats = self.statistics[key][id][current_date]

        
        num_lines = len(content.splitlines())
        num_words = len(content.split())
        num_characters = len(content)

        
        multiplier = -1 if retract else 1

        daily_stats["num_lines"] += num_lines * multiplier
        daily_stats["num_words"] += num_words * multiplier
        daily_stats["num_characters"] += num_characters * multiplier
        daily_stats["count"] += multiplier

        await self.save()   
        
            

        
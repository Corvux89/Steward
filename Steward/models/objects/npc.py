from typing import TYPE_CHECKING
import discord
import uuid
import sqlalchemy as sa

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

class NPC:
    def __init__(self, db: AsyncEngine, guild_id: int, key: str, name: str, **kwargs):
        self._db = db

        self.guild_id = guild_id
        self.key = key
        self.name = name

        self.avatar_url: str = kwargs.get("avatar_url")
        self.roles: list[int] = kwargs.get("roles", [])
        self.adventure_id: uuid.UUID = kwargs.get("adventure_id")

    npc_table = sa.Table(
        "ref_npcs",
        metadata,
        sa.Column("guild_id", sa.BigInteger, nullable=False),
        sa.Column("key", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("avatar_url", sa.String, nullable=True),
        sa.Column("roles", ARRAY(sa.BigInteger), nullable=False, default=[]),
        sa.Column("adventure_id", sa.UUID, nullable=True),
        sa.PrimaryKeyConstraint("guild_id", "key")
    )

    class NPCSchema(Schema):
        db: AsyncEngine

        guild_id = fields.Integer(required=True)
        key = fields.String(required=True)
        name = fields.String(required=True)
        avatar_url = fields.String(required=False, allow_none=True)
        roles = fields.List(fields.Integer, required=True)
        adventure_id = fields.UUID(required=False, allow_none=True)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db

        @post_load
        def make_npc(self, data, **kwargs):
            npc = NPC(self.db, **data)
            return npc
        
    async def delete(self) -> None:
        query = (
            NPC.npc_table.delete()
            .where(
                sa.and_(
                    NPC.npc_table.c.guild_id == self.guild_id,
                    NPC.npc_table.c.key == self.key
                )
            )
        )

        await execute_query(self.db, query, QueryResultType.none)

    async def upsert(self) -> None:
        update_dict = {
            "name": self.name,
            "avatar_url": self.avatar_url,
            "adventure_id": self.adventure_id,
            "roles": self.roles
        }

        insert_dict = {
            "key": self.key,
            "guild_id": self.guild_id,
            **update_dict
        }

        query = (
            insert(NPC.npc_table)
            .values(**insert_dict)
            .returning(NPC.npc_table)
            .on_conflict_do_update(
                index_elements = ["guild_id", "key"],
                set_=update_dict
            )
        )

        await execute_query(self._db, query, QueryResultType.none)

    async def send_message(self, ctx: discord.ApplicationContext, content: str) -> None:
        webhook = await get_webhook(ctx.channel)

        kwargs = {
            "username": self.name,
            "avatar_url": self.avatar_url,
            "content": content
        }

        if isinstance(ctx.channel, discord.Thread):
           kwargs["threat"] = ctx.channel

        await webhook.send(**kwargs)

    async def edit_message(self, ctx: discord.ApplicationContext, message_id: int, content: str) -> None:
        webhook = await get_webhook(ctx.channel)

        kwargs = {
            "content": content
        }

        if isinstance(ctx.channel, discord.Thread):
            kwargs["thread"] = ctx.channel

        await webhook.edit_message(message_id, **kwargs)

    async def register_command(self, bot: "StewardBot"):
        async def npc_command(ctx):
            from Steward.models.objects.webhook import StewardWebhook

            await StewardWebhook(
                ctx,
                type=WebhookType.adventure if self.adventure_id else WebhookType.npc
            ).send()

        if bot.get_command(self.key) is None:
            cmd = commands.Command(npc_command, name=self.key)
            cmd.add_check(dm_check)
            bot.add_command(cmd)

    @staticmethod
    async def get_all(db: AsyncEngine) -> list["NPC"]:
        query = (
            NPC.npc_table.select()
            .order_by(
                NPC.npc_table.c.key.asc()
            )
        )

        npc_rows = await execute_query(db, query, QueryResultType.multiple)

        npcs = [
            NPC.NPCSchema(db).load(dict(row._mapping)) for row in npc_rows
        ]

        return npcs

    
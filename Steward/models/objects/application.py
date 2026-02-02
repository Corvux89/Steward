import sqlalchemy as sa

from marshmallow import Schema, fields, post_load
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from Steward.models.objects.enum import QueryResultType
from Steward.models.objects.player import Player

from ...models import metadata
from ...utils.dbUtils import execute_query


class ApplicationTemplate:
    def __init__(self, db: AsyncEngine, guild_id: int, name: str, **kwargs):
        self._db = db

        self.guild_id = guild_id
        self.name = name
        self.character_specific = kwargs.get('character_specific', False)
        self.template = kwargs.get('template')

    application_template_table = sa.Table(
        "ref_application_templates",
        metadata,
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers .id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("template", sa.String, nullable=True),
        sa.Column("character_specific", sa.BOOLEAN),
        sa.PrimaryKeyConstraint("guild_id", "name")
    )

    class ApplicationTemplateSchema(Schema):
        db: AsyncEngine

        guild_id = fields.Integer(required=True)
        name = fields.String(required=True)
        template = fields.String(required=False, allow_none=True)
        character_specific = fields.Boolean(required=True)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db
            
        @post_load
        def make_application(self, data, **kwargs):
            application = ApplicationTemplate(self.db, **data)
            return application
        
    async def delete(self) -> None:
        query =(
            self.application_template_table.delete()
            .where(
                sa.and_(
                    self.application_template_table.c.guild_id == self.guild_id,
                    self.application_template_table.c.name == self.name
                )
            )
        )

        await execute_query(self._db, query, QueryResultType.none)

    async def upsert(self) -> None:
        update_dict = {
            "template": self.template,
            "character_specific": self.character_specific
        }

        insert_dict = {
            "guild_id": self.guild_id,
            "name": self.name,
            **update_dict
        }

        query = (
            insert(self.application_template_table)
            .values(**insert_dict)
            .returning(self.application_template_table)
            .on_conflict_do_update(
                index_elements = ["guild_id", "name"],
                set_=update_dict
            )
        )

        await execute_query(self._db, query, QueryResultType.none)

    @staticmethod
    async def fetch_all(db: AsyncEngine, guild_id: int) -> list["ApplicationTemplate"]:
        query = (
            ApplicationTemplate.application_template_table.select()
            .where(ApplicationTemplate.application_template_table.c.guild_id == guild_id)
            .order_by(ApplicationTemplate.application_template_table.c.name)
        )

        rows = await execute_query(db, query, QueryResultType.multiple)

        if not rows:
            return []
        
        return [ApplicationTemplate.ApplicationTemplateSchema(db).load(dict(row._mapping)) for row in rows]
    
    @staticmethod
    async def fetch(db: AsyncEngine, guild_id: int, name: str) -> "ApplicationTemplate":
        query = (
            ApplicationTemplate.application_template_table.select()
            .where(
                sa.and_(
                    ApplicationTemplate.application_template_table.c.guild_id == guild_id,
                    ApplicationTemplate.application_template_table.c.name == name
                )
            )
        )

        row = await execute_query(db, query)

        if not row:
            return None
        return ApplicationTemplate.ApplicationTemplateSchema(db).load(dict(row._mapping))
    
class Application:
    def __init__(self, player: "Player", template: "ApplicationTemplate", **kwargs):
        self.player = player
        self.template = template

        self.character = kwargs.get('character')
        self.content = kwargs.get('content', '')

    @property
    def output(self):
        return (
            f"**{self.template.name}**\n"
            f"**Player**: {self.player.mention}\n\n"
            f"{self.content}"
        )



    
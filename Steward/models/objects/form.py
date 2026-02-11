import uuid
import json
from datetime import datetime, timezone
import sqlalchemy as sa

from marshmallow import Schema, fields, post_load
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine
from typing import Optional, TYPE_CHECKING

from Steward.models.objects.enum import QueryResultType
from Steward.models.objects.player import Player

from .. import metadata
from ...utils.dbUtils import execute_query

if TYPE_CHECKING:
    from Steward.models.objects.character import Character


class FormTemplate:
    def __init__(self, db: AsyncEngine, guild_id: int, name: str, **kwargs):
        self._db = db

        self.guild_id = guild_id
        self.name = name
        self.character_specific = kwargs.get('character_specific', False)
        self.content = kwargs.get('content')

    application_template_table = sa.Table(
        "ref_form_templates",
        metadata,
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("content", sa.ARRAY(sa.JSON), nullable=False, default=[]),
        sa.Column("character_specific", sa.BOOLEAN),
        sa.PrimaryKeyConstraint("guild_id", "name")
    )

    class ApplicationTemplateSchema(Schema):
        db: AsyncEngine

        guild_id = fields.Integer(required=True)
        name = fields.String(required=True)
        character_specific = fields.Boolean(required=True)
        content = fields.List(fields.Dict, required=True)
        

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db
            
        @post_load
        def make_application(self, data, **kwargs):
            application = FormTemplate(self.db, **data)
            return application

    async def upsert(self) -> None:
        update_dict = {
            "content": self.content,
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

    async def delete(self) -> None:
        query = (
            self.application_template_table.delete()
            .where(
                sa.and_(
                    self.application_template_table.c.guild_id == self.guild_id,
                    self.application_template_table.c.name == self.name
                )
            )
        )

        await execute_query(self._db, query, QueryResultType.none)

    @staticmethod
    async def fetch_all(db: AsyncEngine, guild_id: int) -> list["FormTemplate"]:
        query = (
            FormTemplate.application_template_table.select()
            .where(FormTemplate.application_template_table.c.guild_id == guild_id)
            .order_by(FormTemplate.application_template_table.c.name)
        )

        rows = await execute_query(db, query, QueryResultType.multiple)

        if not rows:
            return []
        
        return [FormTemplate.ApplicationTemplateSchema(db).load(dict(row._mapping)) for row in rows]
    
    @staticmethod
    async def fetch(db: AsyncEngine, guild_id: int, name: str) -> "FormTemplate":
        query = (
            FormTemplate.application_template_table.select()
            .where(
                sa.and_(
                    FormTemplate.application_template_table.c.guild_id == guild_id,
                    FormTemplate.application_template_table.c.name == name
                )
            )
        )

        row = await execute_query(db, query)

        if not row:
            return None
        return FormTemplate.ApplicationTemplateSchema(db).load(dict(row._mapping))


class Application:
    def __init__(self, db: AsyncEngine, **kwargs):
        self._db = db
        
        self.id: Optional[uuid.UUID] = kwargs.get('id')
        self.guild_id: int = kwargs.get('guild_id')
        self.player_id: int = kwargs.get('player_id')
        self.character_id: Optional[uuid.UUID] = kwargs.get('character_id')
        self.template_name: str = kwargs.get('template_name')
        self.data: dict = kwargs.get('data', {})  # {field_label: value}
        self.status: str = kwargs.get('status', 'draft')  
        self.created_ts = kwargs.get('created_ts')
        self.submitted_ts = kwargs.get('submitted_ts')
        self.message_id: Optional[int] = kwargs.get('message_id')
        
        # These will be populated when fetching
        self.template: Optional[FormTemplate] = kwargs.get('template')
        self.player: Optional[Player] = kwargs.get('player')
        self.character: Optional['Character'] = kwargs.get('character')

    application_table = sa.Table(
        "applications",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers.id"), nullable=False),
        sa.Column("player_id", sa.BigInteger, nullable=False),
        sa.Column("character_id", sa.UUID, sa.ForeignKey("characters.id"), nullable=True),
        sa.Column("template_name", sa.String, nullable=False),
        sa.Column("data", sa.JSON, nullable=False, default={}),
        sa.Column("output", sa.String, nullable=True),
        sa.Column("status", sa.String, nullable=False, default='draft'),
        sa.Column("created_ts", sa.TIMESTAMP(timezone=timezone.utc), nullable=False),
        sa.Column("submitted_ts", sa.TIMESTAMP(timezone=timezone.utc), nullable=True),
        sa.Column("message_id", sa.BigInteger, nullable=True)
    )

    class ApplicationSchema(Schema):
        db: AsyncEngine

        id = fields.UUID(required=False, allow_none=True)
        guild_id = fields.Integer(required=True)
        player_id = fields.Integer(required=True)
        character_id = fields.UUID(required=False, allow_none=True)
        template_name = fields.String(required=True)
        data = fields.Dict(required=True)
        output = fields.String(required=False, allow_none=True)
        status = fields.String(required=False, allow_none=True)
        created_ts = fields.DateTime(required=False, allow_none=True)
        submitted_ts = fields.DateTime(required=False, allow_none=True)
        message_id = fields.Integer(required=False, allow_none=True)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db

        @post_load
        def make_application(self, data, **kwargs):
            return Application(self.db, **data)
        
    @property
    def output(self):
        lines = []
        
        # Header
        if self.template:
            lines.append(f"## {self.template.name}")
        if self.player:
            lines.append(f"**Player**: {self.player.mention}")
        if self.character:
            lines.append(f"**Character**: {self.character.name}")
        
        if self.template or self.player:
            lines.append("")
        
        # Body
        if self.template and self.template.content:
            for field in self.template.content:
                label = field.get('label', '')
                value = self.data.get(label, '')
                if value:  
                    lines.append(f"**{label}:** {value}")
        else:
            for label, value in self.data.items():
                if value:
                    lines.append(f"**{label}:** {value}")
        
        return '\n'.join(lines)

    @staticmethod
    def parse_output(output: str) -> dict:
        data = {}
        
        # Skip header 
        lines = output.split('\n')
        start_idx = 0
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('##') or stripped.startswith('**Player**') or stripped.startswith('**Character**') or not stripped:
                start_idx = i + 1
            else:
                break
        
        # Parse remaining lines as field data
        for line in lines[start_idx:]:
            line = line.strip()
            if ':' in line:
                # Remove markdown formatting
                line = line.replace('**', '')
                parts = line.split(':', 1)
                if len(parts) == 2:
                    label = parts[0].strip()
                    value = parts[1].strip()
                    data[label] = value
        
        return data
    
    async def delete(self):
        query = (
            self.application_table.delete()
            .where(self.application_table.c.id == self.id)
        )

        await execute_query(self._db, query, QueryResultType.none)

    async def upsert(self) -> "Application":        
        update_dict = {
            "data": self.data,
            "output": self.output,
            "status": self.status,
            "message_id": self.message_id
        }
        
        if self.status == 'submitted' and not self.submitted_ts:
            update_dict["submitted_ts"] = datetime.now(timezone.utc)

        insert_dict = {
            "guild_id": self.guild_id,
            "player_id": self.player_id,
            "character_id": self.character_id,
            "template_name": self.template_name,
            "created_ts": datetime.now(timezone.utc),
            **update_dict
        }

        if self.id:
            query = (
                self.application_table.update()
                .where(self.application_table.c.id == self.id)
                .values(**update_dict)
                .returning(self.application_table)
            )
        else:
            query = (
                insert(self.application_table)
                .values(**insert_dict)
                .returning(self.application_table)
            )

        row = await execute_query(self._db, query)
        
        if not row:
            return self
        
        app: "Application" = Application.ApplicationSchema(self._db).load(dict(row._mapping))
        
        app.template = self.template
        app.player = self.player
        app.character = self.character
        
        return app

    async def delete(self) -> None:
        if not self.id:
            return

        query = (
            self.application_table.delete()
            .where(self.application_table.c.id == self.id)
        )

        await execute_query(self._db, query, QueryResultType.none)

    @staticmethod
    async def fetch_draft(
        db: AsyncEngine,
        guild_id: int,
        player_id: int,
        template_name: str,
        character_id: Optional[uuid.UUID] = None
    ) -> Optional["Application"]:
        query = (
            Application.application_table.select()
            .where(
                sa.and_(
                    Application.application_table.c.guild_id == guild_id,
                    Application.application_table.c.player_id == player_id,
                    Application.application_table.c.template_name == template_name,
                    Application.application_table.c.status == 'draft'
                )
            )
        )
        
        if character_id:
            query = query.where(Application.application_table.c.character_id == character_id)
        else:
            query = query.where(Application.application_table.c.character_id.is_(None))
        
        query = query.order_by(Application.application_table.c.created_ts.desc())

        row = await execute_query(db, query)

        if not row:
            return None
        
        return Application.ApplicationSchema(db).load(dict(row._mapping))

    @staticmethod
    async def fetch_by_message_id(
        db: AsyncEngine,
        guild_id: int,
        message_id: int
    ) -> Optional["Application"]:
        query = (
            Application.application_table.select()
            .where(
                sa.and_(
                    Application.application_table.c.guild_id == guild_id,
                    Application.application_table.c.message_id == message_id
                )
            )
        )

        row = await execute_query(db, query)

        if not row:
            return None

        return Application.ApplicationSchema(db).load(dict(row._mapping))
    


    
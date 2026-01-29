from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional, Union
import discord
import sqlalchemy as sa
import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine
from marshmallow import Schema, fields, post_load
from sqlalchemy.dialects.postgresql import ARRAY
from Steward.models import metadata
from Steward.models.automation.context import AutomationContext
from Steward.models.automation.evaluators import evaluate_expression
from Steward.models.objects.enum import QueryResultType
from Steward.models.objects.npc import NPC
from Steward.utils.dbUtils import execute_query
from constants import BOT_OWNERS

if TYPE_CHECKING:
    from .character import Character
    from .player import Player
    from .activityPoints import ActivityPoints
    from .levels import Levels
    from .activity import Activity

class Server(discord.Guild):
    def __init__(self, db: AsyncEngine, guild: discord.Guild, **kwargs):
        self._db = db
        
        for attr in guild.__slots__:
            try:
                setattr(self, attr, getattr(guild, attr))
            except AttributeError:
                pass

        self.max_level = kwargs.get("max_level", 3)
        self.currency_limit_expr = kwargs.get("currency_limit_expr", "10")
        self.xp_limit_expr = kwargs.get("xp_limit_expr", "100")
        self.xp_global_limit_expr = kwargs.get("xp_global_limit_expr", None)
        self.max_characters_expr = kwargs.get("max_characters_expr", "1")
        self.activity_char_count_threshold = kwargs.get("activity_char_count_threshold", 250)
        self.activity_excluded_channels = kwargs.get("activity_excluded_channels", [])
        self.currency_label = kwargs.get("currency_label", "gp")
        self.staff_role_id: int = kwargs.get("staff_role_id")
        self.staff_request_channel_id: int = kwargs.get("staff_request_channel_id")

        # Virtual Attributes
        self.npcs: list[NPC] = []
        self.activity_points: list["ActivityPoints"] = []
        self.levels: list["Levels"] = []
        self.activities: list["Activity"] = []

    @property
    def staff_role(self) -> discord.Role:
        return self.get_role(self.staff_role_id)
    
    @staff_role.setter
    def staff_role(self, value):
        self.staff_role_id = getattr(value, "id", None)

    guilds_table = sa.Table(
        "servers",
        metadata,
        sa.Column("id", sa.BigInteger, primary_key=True, nullable=False),
        sa.Column("max_level", sa.Integer, nullable=False, default=3),
        sa.Column("currency_limit_expr", sa.String(500), nullable=False, default="10"),
        sa.Column("xp_limit_expr", sa.String(500), nullable=False, default="100"),
        sa.Column("xp_global_limit_expr", sa.String(500), nullable=True),
        sa.Column("max_characters_expr", sa.String(500), nullable=False, default="1"),
        sa.Column("activity_char_count_threshold", sa.Integer, nullable=False),
        sa.Column("activity_excluded_channels", ARRAY(sa.BigInteger), nullable=False, default=[]),
        sa.Column("currency_label", sa.String, nullable=False, default="gp"),
        sa.Column("staff_role_id", sa.BigInteger, nullable=True),
        sa.Column("staff_request_channel_id", sa.BigInteger, nullable=True)
    )

    class ServerSchema(Schema):
        id = fields.Integer(required=True)
        max_level = fields.Integer()
        currency_limit_expr = fields.String()
        xp_limit_expr = fields.String()
        xp_global_limit_expr = fields.String()
        max_characters_expr = fields.String()
        activity_char_count_threshold = fields.Integer()
        activity_excluded_channels = fields.List(fields.Integer, allow_none=False)
        currency_label = fields.String()
        staff_role_id = fields.Integer(allow_none=True, required=False)
        staff_request_channel_id = fields.Integer(allow_none=True, required=False)

        @post_load
        def make_guild(self, data, **kwargs) -> dict:
            return data

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

            self.npcs = [NPC.NPCSchema(self._db).load(dict(row._mapping)) for row in rows]

    async def load_acitvity_points(self) -> None:        
        from Steward.models.objects.activityPoints import ActivityPoints
        query = (
            ActivityPoints.activity_points_table.select()
            .where(ActivityPoints.activity_points_table.c.guild_id == self.id)
            .order_by(ActivityPoints.activity_points_table.c.level.asc())
        )

        rows = await execute_query(self._db, query, QueryResultType.multiple)

        if not rows:
            # Our own...cause I'm lazy like that
            default = {
                1: {
                    "msg": 1,
                    "currency": 0,
                    "xp": "50 if character.level < 4 else 100 if character.level < 7 else 150 if character.level < 11 else 200 if character.level < 15 else 250 if character.level < 19 else 300"
                },
                2: {
                    "msg": 3,
                    "currency": 0,
                    "xp": "50 if character.level < 4 else 100 if character.level < 7 else 150 if character.level < 11 else 200 if character.level < 15 else 250 if character.level < 19 else 300"
                },
                3: {
                    "msg": 6,
                    "currency": 0,
                    "xp": "50 if character.level < 4 else 100 if character.level < 7 else 150 if character.level < 11 else 200 if character.level < 15 else 250 if character.level < 19 else 300"
                },
                4: {
                    "msg": 10,
                    "currency": 0,
                    "xp": "50 if character.level < 4 else 100 if character.level < 7 else 150 if character.level < 11 else 200 if character.level < 15 else 250 if character.level < 19 else 300"
                },
                5: {
                    "msg": 15,
                    "currency": 0,
                    "xp": "50 if character.level < 4 else 100 if character.level < 7 else 150 if character.level < 11 else 200 if character.level < 15 else 250 if character.level < 19 else 300"
                },
                6: {
                    "msg": 21,
                    "currency": 0,
                    "xp": "50 if character.level < 4 else 100 if character.level < 7 else 150 if character.level < 11 else 200 if character.level < 15 else 250 if character.level < 19 else 300"
                },
                7: {
                    "msg": 27,
                    "currency": 0,
                    "xp": "50 if character.level < 4 else 100 if character.level < 7 else 150 if character.level < 11 else 200 if character.level < 15 else 250 if character.level < 19 else 300"
                },
                8: {
                    "msg": 34,
                    "currency": 0,
                    "xp": "50 if character.level < 4 else 100 if character.level < 7 else 150 if character.level < 11 else 200 if character.level < 15 else 250 if character.level < 19 else 300"
                },
                9: {
                    "msg": 42,
                    "currency": 0,
                    "xp": "50 if character.level < 4 else 100 if character.level < 7 else 150 if character.level < 11 else 200 if character.level < 15 else 250 if character.level < 19 else 300"
                },
                10: {
                    "msg": 50,
                    "currency": 0,
                    "xp": "50 if character.level < 4 else 100 if character.level < 7 else 150 if character.level < 11 else 200 if character.level < 15 else 250 if character.level < 19 else 300"
                }
            }
            
            upsert_tasks = [
                ActivityPoints(self._db, guild_id=self.id, level=lvl, points=data["msg"], xp_expr=str(data["xp"]), currency_expr=str(data["currency"])).upsert()
                for lvl, data in default.items()
            ]
            results = await asyncio.gather(*upsert_tasks)
            self.activity_points = results
        else:
            self.activity_points = [ActivityPoints.ActivityPointsSchema(self._db).load(dict(row._mapping)) for row in rows]

    async def load_levels(self) -> None:
        from Steward.models.objects.levels import Levels

        query = (
            Levels.level_table.select()
            .where(Levels.level_table.c.guild_id == self.id)
            .order_by(Levels.level_table.c.level.asc())
        )

        rows = await execute_query(self._db, query, QueryResultType.multiple)

        if not rows:
            # 5e Standard XP Ranges
            default = {
                1: 0,
                2: 300,
                3: 900,
                4: 2700,
                5: 6500,
                6: 14000,
                7: 23000,
                8: 34000,
                9: 48000,
                10: 64000,
                11: 85000,
                12: 100000,
                13: 120000,
                14: 140000,
                15: 165000,
                16: 195000,
                17: 225000,
                18: 265000,
                19: 305000,
                20: 335000
            }

            upsert_tasks = [
                Levels(self._db, self.id, lvl, xp).upsert() 
                for lvl, xp in default.items()
            ]
            results = await asyncio.gather(*upsert_tasks)
            self.levels = results
        else:
            self.levels = [Levels.LevelSchema(self._db).load(dict(row._mapping)) for row in rows]

    async def load_activities(self) -> None:
        from .activity import Activity

        query = (
            Activity.activity_table.select()
            .where(
                sa.and_(
                    Activity.activity_table.c.guild_id == self.id,
                    Activity.activity_table.c.active == True
                )
            )
        )

        rows = await execute_query(self._db, query, QueryResultType.multiple)

        if not rows:
            self.activities = []
        else:
            self.activities = [Activity.ActivitySchema(self._db).load(dict(row._mapping)) for row in rows]

    @classmethod
    async def get_or_create(cls, db: AsyncEngine, guild: discord.Guild) -> "Server":
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
                    currency_limit_expr="10",
                    xp_limit_expr="100",
                    max_characters_expr="1",
                    activity_char_count_threshold=250,
                    activity_excluded_channels=[],
                    currency_label="gp"
                )
                .returning(cls.guilds_table)
            )

            row = await execute_query(db, insert_query)

        data = cls.ServerSchema().load(dict(row._mapping))

        server = cls(db, guild, **data)
        await server.load_npcs()
        await server.load_acitvity_points()
        await server.load_levels()
        await server.load_activities()
        
        return server
    
    async def save(self) -> None:
        query = (
            self.guilds_table.update()
            .where(self.guilds_table.c.id == self.id)
            .values(
                max_level = self.max_level,
                currency_limit_expr = self.currency_limit_expr,
                xp_limit_expr = self.xp_limit_expr,
                xp_global_limit_expr = self.xp_global_limit_expr,
                max_characters_expr = self.max_characters_expr,
                activity_char_count_threshold = self.activity_char_count_threshold,
                activity_excluded_channels = self.activity_excluded_channels,
                currency_label = self.currency_label,
                staff_role_id = self.staff_role_id,
                staff_request_channel_id = self.staff_request_channel_id
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

        characters = [Character.CharacterSchema(self._db).load(dict(row._mapping)) for row in rows]

        return characters
    
    def get_xp_for_level(self, level: int) -> int:
        for l in self.levels:
            if level == l.level:
                return l.xp
            
        return 0
    
    def get_tier_for_level(self, level: int) -> int:
        for l in self.levels:
            if level == l.level:
                return l.tier
            
        return 0
    
    def get_level_for_xp(self, xp: int) -> int:
        level = 0

        for l in self.levels:
            if xp >= l.xp:
                level = l.level

        return level
    
    def get_activitypoint_for_points(self, points: int) -> "ActivityPoints":
        point = None

        for a in self.activity_points:
            if points >= a.points:
                point = a

        return point
    
    def max_characters(self, player: "Player") -> int:
        context = AutomationContext(
            player=player,
            server=self,
        )

        try:
            return int(evaluate_expression(self.max_characters_expr, context))
        except:
            return None
            
    
    def currency_limit(self, player: "Player", character: "Character") -> int:
        context = AutomationContext(
            player=player,
            server=self,
            character=character
        )

        try:
            return int(evaluate_expression(self.currency_limit_expr, context))
        except:
            return None
        
    def xp_limit(self, player: "Player", character: "Character") -> int:
        context = AutomationContext(
            player=player,
            server=self,
            character=character
        )

        try:
            return int(evaluate_expression(self.xp_limit_expr, context))
        except:
            return None
        
    def xp_global_limit(self, player: "Player", character: "Character") -> int:
        context = AutomationContext(
            player=player,
            server=self,
            character=character
        )

        try:
            return int(evaluate_expression(self.xp_global_limit_expr, context))
        except:
            return None
        
    @property
    def currency_str(self) -> str:
        return str(self.currency_label) if self.currency_label and self.currency_label != "" else "Currency"
    
    def get_activity(self, act_name: str) -> Optional["Activity"]:
        if not self.activities:
            return None
        
        for activity in self.activities:
            if activity.name.lower() == act_name.lower():
                return activity
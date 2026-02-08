import asyncio
from datetime import datetime, timezone, timedelta
import json
import logging
import uuid
import sqlalchemy as sa

from typing import TYPE_CHECKING, Optional
from marshmallow import Schema, fields, post_load, pre_load
from sqlalchemy.dialects.postgresql import insert, JSONB
from sqlalchemy.ext.asyncio import AsyncEngine
from Steward.models import metadata
from Steward.models.automation.context import AutomationContext
from Steward.models.automation.evaluators import evaluate_expression
from Steward.models.automation.utils import eval_bool, eval_int
from Steward.models.objects.enum import QueryResultType, RuleTrigger
from Steward.models.views.request import StaffRequestView
from Steward.utils.dbUtils import execute_query
from Steward.utils.discordUtils import chunk_text, get_webhook

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ...bot import StewardBot

class StewardRule:
    def __init__(self, db: AsyncEngine, **kwargs):
        self._db = db

        self.id = kwargs.get('id', uuid.uuid4())
        self.guild_id = kwargs.get('guild_id')
        self.name = kwargs.get('name')
        self.trigger: RuleTrigger = kwargs.get('trigger')  
        self.enabled = kwargs.get('enabled', True)
        self.condition_expr = kwargs.get('condition_expr')  
        self.action_data = kwargs.get('action_data')  
        self.created_ts = kwargs.get('created_ts', datetime.now(timezone.utc))
        self.priority = kwargs.get('priority', 0)
        self.schedule_cron = kwargs.get('schedule_cron')  # Cron expression (e.g., "0 0 * * 0" for weekly)
        self.last_run_ts = kwargs.get('last_run_ts')  # Track last execution time  

    def update(self, data: dict) -> "StewardRule":
        if not data:
            return self

        if 'action_data' in data:
            action_value = data.get('action_data')
            if isinstance(action_value, str):
                try:
                    action_value = json.loads(action_value)
                except Exception:
                    import ast
                    try:
                        action_value = ast.literal_eval(action_value)
                    except Exception:
                        pass
            self.action_data = action_value if action_value is not None else {}

        updatable_fields = {
            'name', 'trigger', 'enabled', 'condition_expr', 'priority',
            'schedule_cron', 'guild_id'
        }

        for key in updatable_fields:
            if key in data and data[key] is not None:
                setattr(self, key, data[key])

        return self

    rules_table = sa.Table(
        "rules",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("guild_id", sa.BigInteger, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("trigger", sa.String, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, default=True),
        sa.Column("condition_expr", sa.String(1000), nullable=True),
        sa.Column("action_data", JSONB, nullable=False),  # Changed to JSONB
        sa.Column("priority", sa.Integer, nullable=False, default=0),
        sa.Column("created_ts", sa.TIMESTAMP(timezone=timezone.utc), nullable=False),
        sa.Column("schedule_cron", sa.String(100), nullable=True),  # For cron-style scheduling
        sa.Column("last_run_ts", sa.TIMESTAMP(timezone=timezone.utc), nullable=True),  # Track last execution
        sa.Index("idx_rules_guild_trigger", "guild_id", "trigger", "enabled")
    )

    def _evaluate_template(self, template: str, context: AutomationContext) -> str:
        import logging
        log = logging.getLogger(__name__)

        def split_format_spec(expr: str) -> tuple[str, str | None]:
            depth = 0
            in_single_quote = False
            in_double_quote = False
            for idx in range(len(expr) - 1, -1, -1):
                char = expr[idx]
                if char == "'" and not in_double_quote:
                    in_single_quote = not in_single_quote
                elif char == '"' and not in_single_quote:
                    in_double_quote = not in_double_quote
                elif in_single_quote or in_double_quote:
                    continue
                elif char in ")]}":
                    depth += 1
                elif char in "([{":
                    depth -= 1
                elif char == ":" and depth == 0:
                    return expr[:idx], expr[idx + 1:]
            return expr, None
        
        if not template:
            return ''
        
        log.debug(f"Evaluating template: {template[:100]}...") 
        
        result = []
        i = 0
        while i < len(template):
            start = template.find('{', i)
            if start == -1:
                result.append(template[i:])
                break
            
            # Append text before the expression
            result.append(template[i:start])
            
            # Find matching closing brace, accounting for nested quotes
            depth = 1
            j = start + 1
            in_single_quote = False
            in_double_quote = False
            
            while j < len(template) and depth > 0:
                char = template[j]
                
                if char == "'" and not in_double_quote:
                    in_single_quote = not in_single_quote
                elif char == '"' and not in_single_quote:
                    in_double_quote = not in_double_quote
                elif not in_single_quote and not in_double_quote:
                    if char == '{':
                        depth += 1
                    elif char == '}':
                        depth -= 1
                
                j += 1
            
            if depth != 0:
                # Couldn't find matching brace, just append the rest
                result.append(template[start:])
                break
            
            # Extract and evaluate the expression
            expr = template[start + 1:j - 1]
            log.debug(f"Found expression to evaluate: '{expr}'")
            
            try:
                expr_value, format_spec = split_format_spec(expr)
                value = evaluate_expression(expr_value, context)
                log.debug(f"Expression '{expr}' evaluated to: {value}")
                if value is None:
                    result.append('')
                elif format_spec:
                    result.append(format(value, format_spec))
                else:
                    result.append(str(value))
            except Exception as e:
                log.warning(f"Failed to evaluate template expression '{expr}': {e}")
                result.append(template[start:j])  
            
            i = j
        
        final_result = ''.join(result)
        log.debug(f"Template result: {final_result[:100]}...")
        return final_result

    def evaluate_condition(self, context: AutomationContext) -> bool:
        if not self.condition_expr:
            return True  
        
        try:
            return eval_bool(self.condition_expr, context, default=False)
        except Exception:
            return False

    def should_run_now(self, current_time: Optional[datetime] = None) -> bool:
        """Check if this scheduled rule should run now based on its schedule configuration"""
        if self.trigger != RuleTrigger.scheduled:
            return False
        
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        
        # Check cron-based scheduling
        if self.schedule_cron:
            # Check if it's a shortcut first (looser timing)
            if self.schedule_cron.lower().startswith('@'):
                return self._matches_shortcut(self.schedule_cron.lower(), current_time)
            # Otherwise use standard cron matching
            return self._matches_cron_expression(current_time)
        
        return False

    def _matches_shortcut(self, shortcut: str, current_time: datetime) -> bool:
        """
        Check if a shortcut schedule should run now.
        Shortcuts use looser timing - they check if the rule has run in the current period.
        
        - @hourly: Run once per hour (any time this hour)
        - @daily/@midnight: Run once per day (any time today)
        - @weekly: Run once per week (any time this week, week starts Monday)
        - @monthly: Run once per month (any time this month)
        - @yearly/@annually: Run once per year (any time this year)
        """
        if not self.last_run_ts:
            return True  # Never run before, should run now
        
        last_run = self.last_run_ts
        
        # Prevent running multiple times in quick succession
        if (current_time - last_run) < timedelta(minutes=1):
            return False
        
        if shortcut == '@hourly':
            # Run if we haven't run this hour
            return (current_time.year != last_run.year or 
                    current_time.month != last_run.month or 
                    current_time.day != last_run.day or 
                    current_time.hour != last_run.hour)
        
        elif shortcut in ('@daily', '@midnight'):
            # Run if we haven't run today
            return (current_time.year != last_run.year or 
                    current_time.month != last_run.month or 
                    current_time.day != last_run.day)
        
        elif shortcut == '@weekly':
            # Run if we haven't run this week (week starts Monday)
            current_week = current_time.isocalendar()[:2]  # (year, week)
            last_week = last_run.isocalendar()[:2]
            return current_week != last_week
        
        elif shortcut == '@monthly':
            # Run if we haven't run this month
            return (current_time.year != last_run.year or 
                    current_time.month != last_run.month)
        
        elif shortcut in ('@yearly', '@annually'):
            # Run if we haven't run this year
            return current_time.year != last_run.year
        
        # Unknown shortcut, fall back to False
        return False

    def _matches_cron_expression(self, current_time: datetime) -> bool:
        """
        Check if current_time matches the cron expression.
        Simplified cron: minute hour day_of_month month day_of_week
        Supports: numbers, *, ranges (1-5), lists (1,3,5), step values (*/5), and shortcuts (@hourly, @daily, etc)
        """
        if not self.schedule_cron:
            return False
        
        # If we ran recently (within last minute), don't run again
        if self.last_run_ts:
            time_since_last_run = current_time - self.last_run_ts
            if time_since_last_run < timedelta(minutes=1):
                return False
        
        try:
            # Convert shortcuts to standard cron expressions
            cron_expr = self._expand_cron_shortcut(self.schedule_cron.strip())
            
            parts = cron_expr.split()
            if len(parts) != 5:
                return False
            
            minute_expr, hour_expr, day_expr, month_expr, dow_expr = parts
            
            # Current time components
            current_minute = current_time.minute
            current_hour = current_time.hour
            current_day = current_time.day
            current_month = current_time.month
            current_dow = current_time.weekday()  # Monday=0, Sunday=6
            
            # Check each component
            if not self._cron_matches(minute_expr, current_minute, 0, 59):
                return False
            if not self._cron_matches(hour_expr, current_hour, 0, 23):
                return False
            if not self._cron_matches(day_expr, current_day, 1, 31):
                return False
            if not self._cron_matches(month_expr, current_month, 1, 12):
                return False
            if not self._cron_matches(dow_expr, current_dow, 0, 6):
                return False
            
            return True
        except Exception:
            return False

    def _expand_cron_shortcut(self, cron_expr: str) -> str:
        """
        Expand cron shortcuts to standard cron expressions.
        
        Supported shortcuts:
        - @yearly, @annually: 0 0 1 1 * (once a year)
        - @monthly: 0 0 1 * * (first day of month)
        - @weekly: 0 0 * * 0 (every Sunday)
        - @daily, @midnight: 0 0 * * * (every day)
        - @hourly: 0 * * * * (every hour)
        """
        shortcuts = {
            '@yearly': '0 0 1 1 *',
            '@annually': '0 0 1 1 *',
            '@monthly': '0 0 1 * *',
            '@weekly': '0 0 * * 0',
            '@daily': '0 0 * * *',
            '@midnight': '0 0 * * *',
            '@hourly': '0 * * * *',
        }
        
        cron_lower = cron_expr.lower()
        if cron_lower in shortcuts:
            return shortcuts[cron_lower]
        
        return cron_expr
    
    def _cron_matches(self, expression: str, value: int, min_val: int, max_val: int) -> bool:
        """Check if a value matches a cron expression component"""
        day_map = {
            "mon": 0,
            "tue": 1,
            "wed": 2,
            "thu": 3,
            "fri": 4,
            "sat": 5,
            "sun": 6,
        }

        def normalize_token(token: str) -> str:
            lowered = token.strip().lower()
            if lowered.isdigit():
                return lowered
            if lowered in day_map:
                return str(day_map[lowered])
            raise ValueError(f"Invalid cron token: {token}")

        if expression == '*':
            return True
        
        # Handle step values (*/5)
        if '/' in expression:
            parts = expression.split('/')
            if parts[0] == '*':
                try:
                    step = int(parts[1])
                    return value % step == 0
                except ValueError:
                    return False
            else:
                # Range with step (1-10/2)
                range_part = parts[0]
                try:
                    step = int(parts[1])
                except ValueError:
                    return False
                if '-' in range_part:
                    try:
                        start_token, end_token = range_part.split('-')
                        start = int(normalize_token(start_token))
                        end = int(normalize_token(end_token))
                    except ValueError:
                        return False
                    return start <= value <= end and (value - start) % step == 0
        
        # Handle ranges (1-5)
        if '-' in expression:
            try:
                start_token, end_token = expression.split('-')
                start = int(normalize_token(start_token))
                end = int(normalize_token(end_token))
            except ValueError:
                return False
            return start <= value <= end
        
        # Handle lists (1,3,5)
        if ',' in expression:
            try:
                values = [int(normalize_token(v)) for v in expression.split(',')]
            except ValueError:
                return False
            return value in values
        
        # Exact match
        try:
            return int(normalize_token(expression)) == value
        except ValueError:
            return False

    async def mark_as_run(self, run_time: Optional[datetime] = None) -> None:
        """Update the last_run_ts field after executing a scheduled rule"""
        if run_time is None:
            run_time = datetime.now(timezone.utc)
        
        self.last_run_ts = run_time
        await self.upsert()

    async def execute_action(self, bot: "StewardBot", context: AutomationContext) -> dict:
        import discord
        
        try:
            setattr(context, "rule", self)
            actions = self.action_data if isinstance(self.action_data, list) else [self.action_data]
            results = []
            
            for action in actions:
                if not isinstance(action, dict):
                    continue
                    
                action_type = action.get('type')

                # TODO: Assign Role, Remove Role
                match action_type:
                    case'reward':
                        await self._reward(action, bot, context, results)

                    case 'message':
                        await self._message(action, bot, context, results)

                    case 'reset_limited':
                        await self._reset_limited(action, bot, context, results)

                    case "staff_points":
                        await self._staff_points(action, bot, context, results)

                    case "post_request":
                        await self._post_request(action, bot, context, results)  

                    case "post_application":
                        await self._post_application(action, bot, context, results)

                    case "bulk_reward":
                        await self._bulk_reward(action, bot, context, results)

                    case "assign_role":
                        await self._assign_role(action, bot, context, results)

                    case "remove_role":
                        await self._assign_role(action, bot, context, results)

                        
            return {"success": True, "results": results}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def upsert(self) -> "StewardRule":
        update_dict = {
            "name": self.name,
            "trigger": self.trigger.name,
            "enabled": self.enabled,
            "condition_expr": self.condition_expr,
            "action_data": self.action_data,  # Changed
            "priority": self.priority,
            "schedule_cron": self.schedule_cron,
            "last_run_ts": self.last_run_ts
        }

        insert_dict = {
            "id": self.id,
            "guild_id": self.guild_id,
            "created_ts": self.created_ts,
            **update_dict
        }

        query = (
            insert(StewardRule.rules_table)
            .values(**insert_dict)
            .returning(StewardRule.rules_table)
            .on_conflict_do_update(
                index_elements=["id"],
                set_=update_dict
            )
        )

        row = await execute_query(self._db, query)
        return StewardRule.RuleSchema(self._db).load(dict(row._mapping))

    @staticmethod
    async def get_rules_for_trigger(db: AsyncEngine, guild_id: int, trigger: str) -> list["StewardRule"]:
        query = (
            StewardRule.rules_table.select()
            .where(
                sa.and_(
                    StewardRule.rules_table.c.guild_id == guild_id,
                    StewardRule.rules_table.c.trigger == trigger,
                    StewardRule.rules_table.c.enabled == True
                )
            )
            .order_by(StewardRule.rules_table.c.priority.desc())
        )

        rows = await execute_query(db, query, QueryResultType.multiple)
        return [StewardRule.RuleSchema(db).load(dict(row._mapping)) for row in rows]
    
    @staticmethod
    async def get_all_rules_for_server(db: AsyncEngine, guild_id: int) -> list["StewardRule"]:
        query = (
            StewardRule.rules_table.select()
            .where(
                StewardRule.rules_table.c.guild_id == guild_id
            )
            .order_by(StewardRule.rules_table.c.name.desc())
        )

        rows = await execute_query(db, query, QueryResultType.multiple)
        return [StewardRule.RuleSchema(db).load(dict(row._mapping)) for row in rows]

    @staticmethod
    async def get_all_scheduled_rules(db: AsyncEngine) -> list["StewardRule"]:
        """Get all enabled scheduled rules across all guilds"""
        query = (
            StewardRule.rules_table.select()
            .where(
                sa.and_(
                    StewardRule.rules_table.c.trigger == "scheduled",
                    StewardRule.rules_table.c.enabled == True,
                    StewardRule.rules_table.c.schedule_cron.isnot(None)
                )
            )
            .order_by(StewardRule.rules_table.c.priority.desc())
        )

        rows = await execute_query(db, query, QueryResultType.multiple)
        return [StewardRule.RuleSchema(db).load(dict(row._mapping)) for row in rows]

    class RuleSchema(Schema):
        db: AsyncEngine

        id = fields.UUID(required=True)
        guild_id = fields.Integer(required=True)
        name = fields.String(required=True)
        trigger = fields.String(required=True)
        enabled = fields.Boolean(required=True)
        condition_expr = fields.String(allow_none=True)
        action_data = fields.Field(required=True)  
        priority = fields.Integer(required=True)
        created_ts = fields.DateTime(required=True)
        schedule_cron = fields.String(allow_none=True)  
        last_run_ts = fields.DateTime(allow_none=True)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db

        @pre_load
        def process_action_data(self, data, **kwargs):
            if 'action_data' in data:
                action_data = data['action_data']
                if isinstance(action_data, str):
                    try:
                        data['action_data'] = json.loads(action_data)
                    except Exception as e:
                        pass
            return data

        @post_load
        def make_rule(self, data, **kwargs) -> "StewardRule":
            data['trigger'] = RuleTrigger.from_string(data['trigger'])
            return StewardRule(self.db, **data)
    
    @staticmethod
    async def fetch(db: AsyncEngine, guild_id: int, **kwargs):
        id = kwargs.get('id')
        if id and isinstance(id, str):
            id = uuid.UUID(id)

        name = kwargs.get('name')

        query = (
            StewardRule.rules_table.select()
            .where(StewardRule.rules_table.c.guild_id == guild_id)
        )

        if id:
            query = query.where(StewardRule.rules_table.c.id == id)
        elif name:
            query = query.where(StewardRule.rules_table.c.name == name)

        row = await execute_query(db, query)

        if not row:
            return None
        
        return StewardRule.RuleSchema(db).load(dict(row._mapping))
    
    async def _reward(self, action: dict, bot: "StewardBot", context: "AutomationContext", results: []):
        from .log import StewardLog
        from .enum import LogEvent

        await StewardLog.create(
            bot,
            author=bot.user,
            player=context.player,
            character=context.character,
            event=LogEvent.automation,
            activity=action.get('activity'),
            currency=action.get('currency', 0),
            xp=action.get('xp', 0),
            notes=f"Rule: {self.name}\n{action.get('notes')}"
        )

        results.append({'type': self.trigger.name, 'success': True})

    async def _message(self, action: dict, bot: "StewardBot", context: "AutomationContext", results: []):
        import discord

        channel_id = action.get('channel_id')

        if channel_id:
            channel = bot.get_channel(int(channel_id))
            if not channel:
                results.append({'type': self.trigger.name, 'success': False, 'error': f'Channel {channel_id} not found'})
                return
        elif context.ctx and hasattr(context.ctx, "channel"):
            channel = context.ctx.channel
        else:
            results.append({'type': self.trigger.name, 'success': False, 'error': f'No channel available'})
            return
            
        content_template = action.get('content', '')
        message_content = self._evaluate_template(content_template, context)
        embed_data = action.get('embed')

        embed = None
        if embed_data:
            title = self._evaluate_template(embed_data.get('title', ''), context)
            description = self._evaluate_template(embed_data.get('description', ''), context)
            
            embed = discord.Embed(
                title=title if title else None,
                description=description if description else None,
                color=embed_data.get('color', discord.Color.blue())
            )
            
            fields = embed_data.get('fields', [])
            for field in fields:
                field_name = self._evaluate_template(field.get('name', ''), context)
                field_value = self._evaluate_template(field.get('value', ''), context)
                embed.add_field(
                    name=field_name,
                    value=field_value,
                    inline=field.get('inline', False)
                )
            
            if footer := embed_data.get('footer'):
                footer_text = self._evaluate_template(footer, context)
                embed.set_footer(text=footer_text)
            
            if thumbnail := embed_data.get('thumbnail'):
                thumbnail = self._evaluate_template(thumbnail, context)
                embed.set_thumbnail(url=thumbnail)

            if timestamp := embed_data.get('timestamp'):
                try:
                    timestamp = self._evaluate_template(timestamp, context)
                    embed.timestamp = datetime.fromisoformat(timestamp)
                except:
                    pass
        
        if message_content or embed:
            await channel.send(content=message_content or None, embed=embed)
            results.append({'type': self.trigger.name, 'success': True})
        else:
            results.append({'type': self.trigger.name, 'success': False, 'error': 'No content or embed'})

    async def _reset_limited(self, action: dict, bot: "StewardBot", context: "AutomationContext", results: []):
        characters = await context.server.get_all_characters()
        tasks = []

        for character in characters:
            if action.get('xp', True) == True:
                character.limited_xp = 0
            if action.get('currency', True) == True:
                character.limited_currency = 0
            if action.get('activity_points', True) == True:
                character.activity_points = 0
            tasks.append(character.upsert())

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        results.append({'type': self.trigger.name, 'success': True, 'count': len(characters)})

    async def _bulk_reward(self, action: dict, bot: "StewardBot", context: "AutomationContext", results: []):
        from .log import StewardLog
        from .enum import LogEvent

        players = await context.server.get_all_players()
        tasks = []

        if not players:
            results.append({'type': self.trigger.name, 'success': False, 'error': 'No players found in the server'})

        for player in players:
            ctx = AutomationContext(player=player, server=context.server)

            if not player.active_characters:
                continue
            
            if eval_bool(action.get('condition', ''), ctx) == True:
                tasks.append(StewardLog.create(
                    bot,
                    author=bot.user,
                    player=player,
                    character=player.primary_character,
                    event=LogEvent.automation,
                    activity=action.get('activity'),
                    currency=action.get('currency', 0),
                    xp=action.get('xp', 0),
                    notes=f"Rule: {self.name}\n{action.get('notes')}"
                ))
            
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        results.append({'type': self.trigger.name, 'success': True, 'count': len(tasks)})

    async def _staff_points(self, action: dict, bot: "StewardBot", context: "AutomationContext", results: []):
        if hasattr(context, "log") and context.log is not None:
            context.player = context.log.author
        elif self.trigger not in [RuleTrigger.staff_point, RuleTrigger.log]:
            results.append({'type': self.trigger.name, 'success': False, 'error': f'Improper context/trigger'})
            return
        
        if context.player.bot:
            results.append({'type': self.trigger.name, 'success': False, 'error': f'Can\'t do this for a  a bot'})
            return
        
        value_expr = str(action.get('value', 0))

        amount = eval_int(value_expr, context)

        context.player.staff_points = max(context.player.staff_points+amount, 0)

        await context.player.save()
        results.append({'type': self.trigger.name, 'success': True})

        if self.trigger != RuleTrigger.staff_point:
            bot.dispatch(RuleTrigger.staff_point.name, context.player)

    async def _post_request(self, action: dict, bot: "StewardBot", context: "AutomationContext", results: []):
        if self.trigger != RuleTrigger.new_request:
            results.append({'type': self.trigger.name, 'success': False, 'error': f'Improper trigger'})
        elif not hasattr(context, "request"):
            results.append({'type': self.trigger.name, 'success': False, 'error': f'Request not found'})

        channel_id = action.get('channel_id')

        if channel_id:
            channel = bot.get_channel(int(channel_id))
            if not channel:
                await context.request.delete()
                results.append({'type': self.trigger.name, 'success': False, 'error': f'Channel {channel_id} not found'})
                return
        elif context.ctx and hasattr(context.ctx, "channel"):
            channel = context.ctx.channel
        else:
            await context.request.delete()
            results.append({'type': self.trigger.name, 'success': False, 'error': f'No channel available'})
            return
        try:
            if context.request.staff_message:
                view = StaffRequestView(bot, request=context.request, action=action)
                await context.request.staff_message.edit(view=view)
            else:
                message = await channel.send(content="Incoming request")
                context.request.staff_message = message
                context.request.staff_message_id = message.id
                context.request.staff_channel_id = channel.id
                await context.request.upsert()

                view = StaffRequestView(bot, request=context.request, action=action)
                await message.edit(view=view, content=None)
            results.append({'type': self.trigger.name, 'success': True})
        except Exception as e:
            await context.request.delete()
        
    async def _post_application(self, action: dict, bot: "StewardBot", context: "AutomationContext", results: []):
        from Steward.models.objects.form import Application

        if self.trigger != RuleTrigger.new_application:
            results.append({'type': self.trigger.name, 'success': False, 'error': f'Improper trigger'})
        elif not hasattr(context, "application"):
            results.append({'type': self.trigger.name, 'success': False, 'error': f'Application not found'})

        channel_id = action.get('channel_id')

        if channel_id:
            channel = bot.get_channel(int(channel_id))
            if not channel:
                await context.request.delete()
                results.append({'type': self.trigger.name, 'success': False, 'error': f'Channel {channel_id} not found'})
                return
        elif context.ctx and hasattr(context.ctx, "channel"):
            channel = context.ctx.channel
        else:
            await context.request.delete()
            results.append({'type': self.trigger.name, 'success': False, 'error': f'No channel available'})
            return
        
        application: Application = context.application

        webhook = await get_webhook(channel)

        chunks = chunk_text(application.output)

        if application.message_id:
            await webhook.edit_message(
                application.message_id,
                content=chunks[0]
            )

            if len(chunks) > 1:
                log.info("too many chunks")
        else:
            for i, chunk in enumerate(chunks):
                if i == 0:
                    message = await webhook.send(
                        username=application.player.display_name if application.template.character_specific == False else application.character.name,
                        avatar_url=(
                            application.player.avatar.url if application.player.avatar else None if application.template.character_specific == False else application.character.avatar_url
                        ),
                        content=chunk,
                        wait=True
                    )

                    application.message_id = message.id
                    await application.upsert()

                    if application.template.character_specific:
                        name = application.character.name
                    else:
                        name = application.player.display_name

                    thread = await message.create_thread(
                        name=f"{name} - {application.template.name}",
                        auto_archive_duration=10080
                    )
                else:
                    await thread.send(chunk)

            await thread.send(
                f"Need to make an edit? Use `/edit_application` in this thread."
            )

        results.append({'type': self.trigger.name, 'success': True})

    async def _assign_role(self, action: dict, bot: "StewardBot", context: "AutomationContext", results: []):
        role_id = action.get("role_id")
        reason = action.get("reason", f"Automated role action per rule {self.name}")

        if not hasattr(context, "server"):
            results.append({'type': self.trigger.name, 'success': False, 'error': f'Server not found'})
            return
        else:
            server = context.server

        if role_id:
            role = server.get_role(int(role_id))

            if not role:
                results.append({'type': self.trigger.name, 'success': False, 'error': f'Role {role_id} not found'})
                return
            
        if role not in context.player.roles:
            await context.player.add_roles(role, reason=reason)
        results.append({'type': self.trigger.name, 'success': True})

    async def _remove_role(self, action: dict, bot: "StewardBot", context: "AutomationContext", results: []):
        role_id = action.get("role_id")
        reason = action.get("reason", f"Automated role action per rule {self.name}")

        if not hasattr(context, "server"):
            results.append({'type': self.trigger.name, 'success': False, 'error': f'Server not found'})
            return
        else:
            server = context.server

        if role_id:
            role = server.get_role(int(role_id))

            if not role:
                results.append({'type': self.trigger.name, 'success': False, 'error': f'Role {role_id} not found'})
                return
            
        if role in context.player.roles:
            await context.player.remove_roles(role, reason=reason)
        results.append({'type': self.trigger.name, 'success': True})


        
    







from decimal import Decimal
import uuid
import sqlalchemy as sa
import discord

from typing import TYPE_CHECKING, Union
from marshmallow import Schema, fields, post_load
from datetime import datetime, timezone

from Steward.models.automation.utils import eval_numeric
from ..automation.context import AutomationContext
from Steward.models.objects.activity import Activity
from Steward.models.objects.enum import LogEvent, RuleTrigger
from Steward.models import metadata
from Steward.models.objects.exceptions import StewardError, TransactionError
from Steward.utils.dbUtils import execute_query

if TYPE_CHECKING:
    from ...bot import StewardBot
    from .player import Player
    from .character import Character
    from .servers import Server

class StewardLog:
    """
    Represents a log entry in the Steward system for tracking player activities, transactions, and events.
    This class manages log entries that track various events such as character activities,
    currency transactions, and experience point (XP) gains/losses. It provides methods for
    creating, fetching, and persisting log entries to the database.
    Attributes:
        id (uuid.UUID): Unique identifier for the log entry.
        author_id (int): Discord user ID of the author who created the log entry.
        player_id (int): Discord user ID of the player associated with the log entry.
        guild_id (int): Discord guild ID where the log entry was created.
        event (LogEvent): The type of event being logged.
        character_id (uuid.UUID, optional): ID of the character associated with the log entry.
        activity (Activity): The activity associated with this log entry.
        currency (Decimal): Amount of currency gained or spent in this transaction.
        xp (Decimal): Amount of experience points gained or spent in this transaction.
        notes (str, optional): Additional notes or description for the log entry.
        invalid (bool): Flag indicating if the log entry has been invalidated.
        created_ts (datetime): Timestamp when the log entry was created (UTC).
        server (Server): Server object associated with the log entry.
        player (Player): Player object associated with the log entry.
        author (Union[Player, discord.User]): Author object who created the log entry.
        character (Character, optional): Character object associated with the log entry.
        activity_id (uuid.UUID, optional): ID of the activity associated with the log entry.
    Methods:
        upsert(): Inserts or updates the log entry in the database.
        fetch(bot, log_id, **kwargs): Retrieves a log entry by its ID.
        create(bot, author, player, event, **kwargs): Creates a new log entry with validation and updates.
    Properties:
        epoch_time: Returns the timestamp as a Unix epoch integer.
    Example:
        >>> log = await StewardLog.create(
        ...     bot=bot,
        ...     author=author,
        ...     player=player,
        ...     event=LogEvent.ACTIVITY,
        ...     character=character,
        ...     currency=100,
        ...     xp=50
        ... )
    """

    def __init__(self, bot: "StewardBot", **kwargs):
        self._bot = bot

        self.id = kwargs.get("id")
        self.author_id = kwargs.get("author_id")
        self.player_id = kwargs.get("player_id")
        self.guild_id = kwargs.get("guild_id")
        self.event: LogEvent = kwargs.get("event")
        self.character_id = kwargs.get("character_id")
        self.activity: Activity = kwargs.get("activity")
        self.currency: Decimal = kwargs.get("currency", 0)
        self.xp: Decimal = kwargs.get("xp", 0)
        self.notes = kwargs.get("notes")
        self.invalid = kwargs.get("invalid", False)
        self.created_ts: datetime = kwargs.get("created_ts", datetime.now(timezone.utc))

        self.original_xp: Decimal = kwargs.get("original_xp", 0)
        self.original_currency: Decimal = kwargs.get("original_currency", 0)

        self.server: "Server" = kwargs.get("server")
        self.player: "Player" = kwargs.get("player")
        self.author: Union["Player", discord.User] = kwargs.get("author")
        self.character: "Character" = kwargs.get("character")
        self.activity_id = kwargs.get("activity_id")

    log_table = sa.Table(
        "logs",
        metadata,
        sa.Column("id", sa.UUID, primary_key=True, default=uuid.uuid4),
        sa.Column("author_id", sa.BigInteger, nullable=False),
        sa.Column("player_id", sa.BigInteger, nullable=False),
        sa.Column("guild_id", sa.BigInteger, sa.ForeignKey("servers.id"), nullable=False),
        sa.Column("event", sa.String, nullable=False),
        sa.Column("character_id", sa.UUID, sa.ForeignKey("characters.id"), nullable=True),
        sa.Column("activity_id", sa.UUID, sa.ForeignKey("activities.id"), nullable=True),
        sa.Column("original_currency", sa.DECIMAL, nullable=False),
        sa.Column("currency", sa.DECIMAL, nullable=False),
        sa.Column("original_xp", sa.DECIMAL, nullable=False),
        sa.Column("xp", sa.DECIMAL, nullable=False),
        sa.Column("notes", sa.String, nullable=True),
        sa.Column("invalid", sa.Boolean, nullable=False, default=False),
        sa.Column("created_ts", sa.TIMESTAMP(timezone=timezone.utc), nullable=False),
        sa.Index("idx_log_guild_player", "guild_id", "player_id"),
        sa.Index("idx_log_guild_author", "guild_id", "author_id")
    )

    class StewardLogSchema(Schema):
        id = fields.UUID(required=True)
        author_id = fields.Integer()
        player_id = fields.Integer()
        guild_id = fields.Integer()
        event = fields.String()
        character_id = fields.UUID(allow_none=True, required=False)
        activity_id = fields.UUID(allow_none=True, required=False)
        original_currency = fields.Decimal(places=2)
        currency = fields.Decimal(places=2)
        original_xp = fields.Decimal(places=2)
        xp = fields.Decimal(places=2)
        notes = fields.String(allow_none=True, required=False)
        invalid = fields.Boolean()
        created_ts = fields.DateTime("timestamp")

        @post_load
        def make_log(self, data, **kwargs) -> dict:
            return data   

    @property
    def epoch_time(self) -> int:
        return int(self.created_ts.timestamp())

    async def upsert(self) -> "StewardLog":
        update_dict = {
            "event": self.event.name,
            "activity_id": self.activity.id if hasattr(self, "activity") and self.activity else self.activity_id if hasattr(self, "activity_id") and self.activity_id else None,
            "notes": getattr(self, "notes", None),
            "original_currency": self.original_currency,
            "currency": self.currency,
            "original_xp": self.original_xp,
            "xp": self.xp,
            "invalid": self.invalid
        }

        insert_dict = {
            "author_id": self.author.id,
            "player_id": self.player.id,
            "guild_id": self.server.id,
            "created_ts": datetime.now(timezone.utc),
            "character_id": self.character.id if hasattr(self, "character") and self.character else None,
            **update_dict
        }

        if hasattr(self, "id") and self.id is not None:
            query = (
                StewardLog.log_table.update()
                .where(StewardLog.log_table.c.id == self.id)
                .values(**update_dict)
                .returning(StewardLog.log_table)
            )
        else:
            query = (
                StewardLog.log_table.insert()
                .values(**insert_dict)
                .returning(StewardLog.log_table)
            )

        row = await execute_query(self._bot.db, query)

        if not row:
            return None
        
        data = StewardLog.StewardLogSchema().load(dict(row._mapping))

        log = await StewardLog._make_log_whole(self._bot, data)

        return log    
        
    @staticmethod
    async def fetch(bot: "StewardBot", log_id: Union[uuid.UUID, str], **kwargs) -> "StewardLog":
        from Steward.models.objects.servers import Server
        from Steward.models.objects.player import Player

        if isinstance(log_id, str):
            log_id = uuid.UUID(log_id)

        query = (
            StewardLog.log_table.select()
            .where(StewardLog.log_table.c.id == log_id)
        )

        row = await execute_query(bot.db, query)

        if not row:
            return None

        data = StewardLog.StewardLogSchema().load(dict(row._mapping))

        log = await StewardLog._make_log_whole(bot, data)

        return log

    @staticmethod
    async def _make_log_whole(bot: "StewardBot", data):
        from Steward.models.objects.character import Character
        from Steward.models.objects.servers import Server
        from Steward.models.objects.player import Player

        log = StewardLog(bot, **data)
        log.event = LogEvent.from_string(log.event)
        log.server = await Server.get_or_create(bot.db, bot.get_guild(log.guild_id))
        log.player = await Player.get_or_create(bot.db, log.server.get_member(log.player_id))
        log.author = await Player.get_or_create(bot.db, log.server.get_member(log.author_id))
        log.character = await Character.fetch(bot.db, log.character_id)
        log.activity = await Activity.fetch(bot.db, log.activity_id)
        
        return log
    
    @staticmethod
    async def create(bot: "StewardBot",author: Union["Player", discord.User], player: "Player", event: LogEvent, **kwargs):
        """
        Create a new log entry for a player action or event.
        This method handles the creation of log entries with associated currency and XP changes,
        applying server limits and validations as needed.
        Args:
            bot (StewardBot): The bot instance with database access.
            author (Union[Player, discord.User]): The user who initiated the log entry.
            player (Player): The player associated with this log entry.
            event (LogEvent): The type of event being logged.
            **kwargs: Additional keyword arguments:
                character_id (int, optional): The ID of the character to fetch.
                character (Character, optional): The character object directly.
                activity (Union[str, Activity], optional): The activity associated with this log.
                notes (str, optional): Additional notes for the log entry.
                currency (Union[int, str], optional): Currency change amount or expression.
                xp (Union[int, str], optional): XP change amount or expression.
        Returns:
            StewardLog: The created log entry object.
        Raises:
            StewardError: If a character is required but not specified for XP/currency changes.
            TransactionError: If the character cannot afford the currency cost or would drop below 0 XP.
        Notes:
            - Currency and XP expressions are evaluated in the automation context.
            - If the activity is limited, server-defined limits are applied.
            - Character updates are persisted before returning the log entry.
        """
        from Steward.models.objects.servers import Server
        from Steward.models.objects.character import Character

        character_id = kwargs.get("character_id")

        if character_id:
            character = await Character.fetch(bot.db, character_id)
        else:
            character = kwargs.get("character")

        server = await Server.get_or_create(bot.db, bot.get_guild(player.guild.id))
        context = AutomationContext(player=player, server=server, character=character, patrol=kwargs.get("patrol"))

        act: "Activity" = kwargs.get("activity")
        activity = None
        if isinstance(act, str):
            activity = server.get_activity(act)

            if activity is None:
                raise StewardError(f"Activity `{act}` not found.")
        elif isinstance(act, Activity):
            activity = act

        notes = kwargs.get("notes")

        currency = kwargs.get("currency", activity.currency_expr if activity else 0)
        if isinstance(currency, str):
            currency = eval_numeric(currency, context)

        xp = kwargs.get("xp", activity.xp_expr if activity else 0)
        if isinstance(xp, str):
            xp = eval_numeric(xp, context)

        original_currency = currency
        original_xp = xp
        # Validations
        if activity and activity.limited:
            currency_limit = server.currency_limit(player, character)
            xp_limit = server.xp_limit(player, character)

            if xp_limit:
                xp = min(xp, xp_limit-character.limited_xp)

            if currency_limit:
                currency = min(currency, currency_limit-character.limited_currency)

        # Type Conversions
        currency = Decimal(currency)
        xp = int(xp)

        if (xp > 0 or currency > 0) and not character:
            raise StewardError(
                "Need to specify a character to do this for."
            )
        
        elif character and currency < 0 and character.currency + currency < 0:
            raise TransactionError(
                f"{character.name} // {player.display_name} cannot afford the {currency:,} {server.currency_str} cost."
                )
        
        elif character and xp < 0 and character.xp + xp <0:
            raise TransactionError(
                f"{character.name} // {player.display_name} cannot drop below `0` xp"
            )
        
        # Updates
        if character:
            character.currency += currency
            
            if server.xp_global_limit_expr and server.xp_global_limit_expr != "":
                character.xp += min(xp,server.xp_global_limit(player, character))

            if activity and activity.limited:
                character.limited_currency += currency
                character.limited_xp += xp


        log_entry = StewardLog(
            bot,
            author=author,
            player=player,
            server=server,
            event=event,
            activity_id=activity.id if activity else  None,
            character=character if character else None,
            notes=notes,
            original_currency=round(original_currency,2),
            currency=round(currency,2),
            original_xp=round(original_xp,2),
            xp=round(xp,2)
        )

        if character:
            await character.upsert()

        log_entry = await log_entry.upsert()
        bot.dispatch(RuleTrigger.log.name, log_entry)

        return log_entry      


import sqlalchemy as sa

from decimal import Decimal
from marshmallow import Schema, fields, post_load
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncEngine
from Steward.models import metadata
from Steward.utils.dbUtils import execute_query


class CurrencySystem:
    def __init__(self, db: AsyncEngine, **kwargs):
        self._db = db

        self.guild_id = kwargs.get("guild_id")
        self.base_currency = kwargs.get("base", "gold")
        self.rates: dict[str, Decimal] = kwargs.get("rates", {})

    def to_base(self, amount: Decimal, currency: str) -> Decimal:
        return amount * self.rates[currency]
    
    def from_base(self, amount: Decimal, currency: str) -> Decimal:
        return amount / self.rates[currency]
    
    def convert(self, from_currency: str, to_currency: str, amount: Decimal) -> Decimal:
        base = self.to_base(amount, from_currency)
        converted = self.from_base(base, to_currency)

        return converted

    currency_table = sa.Table(
        "currency_systems",
        metadata,
        sa.Column("guild_id", sa.BigInteger, nullable=False, primary_key=True),
        sa.Column("base_currency", sa.String, nullable=False),
        sa.Column("rates", sa.JSON, nullable=False)
    )

    class CurrencySystemSchema(Schema):
        db: AsyncEngine

        guild_id = fields.Integer(required=True)
        base = fields.String(required=True)
        rates = fields.Dict(required=False, load_default=dict)

        def __init__(self, db: AsyncEngine, **kwargs):
            super().__init__(**kwargs)
            self.db = db

        @post_load
        async def make_system(self, data, **kwargs) -> "CurrencySystem":
            cs = CurrencySystem(self.db, **data)

            return cs
        
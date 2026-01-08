import discord

from typing import List, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from Steward.bot import StewardContext

class RuleContext:
    def __init__(self, ctx: Union["StewardContext", "discord.Interaction"]):
        self.ctx = ctx

class Condition:
    def __init__(self, condition: str):
        self.condition = condition

    def run(self, rulectx)

class Rule:
    def __init__(
            self,
            name: str,
            conditions: List[Condition]
            )
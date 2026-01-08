from enum import Enum, auto

class StewardEnum(Enum):

    @classmethod
    def from_string(cls, value: str) -> "StewardEnum":
        try:
            return cls[value.lower()]
        except KeyError:
            raise ValueError(f"Invalid value: {value}")

class QueryResultType(StewardEnum):
    single = auto()
    multiple = auto()
    scalar = auto()
    none = auto()

class WebhookType(StewardEnum):
    npc = auto()
    adventure = auto()
    character = auto()
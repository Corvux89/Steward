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

class ApplicationType(StewardEnum):
    new = "New Character"
    death = "Death Reroll"
    freeroll = "Free Reroll"
    level = "Level Up"

class LogEvent(StewardEnum):
    player_update = "Player Update"
    new_character = "New Character"
    edit_character = "Edit Character"
    level_up = "Level Up"
    activity = "Activity"
    reward = "Reward"
    null_log = "Null Log"
    automation = "Automated Reward (Rules)"


class RuleTrigger(StewardEnum):
    member_join =  "Member Join"
    member_leave = "Member Leave"
    level_up = "Character Level Up"
    new_character = "New Character"
    inactivate_character = "Inactivate Character"
    log = "Log Created"
    scheduled = "Scheduled"
    staff_point = "Staff Point"
    new_request = "New Request"
    new_application = "New Application"
    patrol_complete = "Patrol Completed"

class PatrolOutcome(StewardEnum):
    extreme_clear = "Extreme Clear"
    full_clear = "Full Clear"
    half_clear = "Half Clear"
    failure = "Failure"
    incomplete = "Incomplete"
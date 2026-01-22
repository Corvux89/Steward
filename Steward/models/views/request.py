

from Steward.bot import StewardBot, StewardContext
from Steward.models.objects.activity import Activity
from Steward.models.objects.character import Character
from Steward.models.views import StewardView


class BaseRequestView(StewardView):
    __copy_attrs__ = [
        "bot", "ctx", "activity"
    ]

    bot: StewardBot
    ctx: StewardContext
    activity: Activity
    characters: list[Character]

class RequestView(BaseRequestView):
    def __init__(self, bot: StewardBot, ctx: StewardContext, **kwargs):
        self.owner = ctx.author
        self.bot = bot
        

    


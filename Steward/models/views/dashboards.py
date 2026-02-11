from datetime import datetime, timezone
import discord.ui as ui
import discord

from Steward.models.objects.dashboards import CategoryDashboard
from Steward.utils.discordUtils import get_last_message_in_channel
from constants import CHANNEL_BREAK, ZWSP3
from ..views import StewardView

BREAK_CHEAK = [
    CHANNEL_BREAK,
    CHANNEL_BREAK.replace(" ", ""),
    "```\n  \n```"    
]

class CategoryDashboardView(StewardView):
    dashboard: CategoryDashboard
    available: list[discord.TextChannel] = []
    unavailable: list[discord.TextChannel] = []

    async def refresh_dashboard(self, message: discord.Message = None):
        dashboard_message: discord.Message = await self.dashboard.message()

        if isinstance(dashboard_message, bool):
            return
        
        if not dashboard_message or not dashboard_message.pinned:
            await self.dashboard.delete()
            return
        
        if message:
            if message.channel.id in self.dashboard.excluded_channel_ids:
                return
            
            self.setup_channels()

            if message.content in BREAK_CHEAK:
                if message.channel in self.available:
                    return
                elif message.channel in self.unavailable:
                    self.unavailable.remove(message.channel)

                self.available.append(message.channel)
            else:
                if message.channel in self.unavailable:
                    return
                elif message.channel in self.available:
                    self.available.remove(message.channel)
                self.unavailable.append(message.channel)

        else:
            self.available = []
            self.unavailable = []
            for channel in self.dashboard.channels:
                if last_message := await get_last_message_in_channel(channel):
                    if last_message and last_message.content in BREAK_CHEAK:
                        self.available.append(channel)
                    elif last_message:
                        self.unavailable.append(channel)
                    else:
                        self.available.append(channel)


        self.clear_items()

        self.items = [
            ui.Container(
                ui.TextDisplay(f"### Channel Statuses - {self.dashboard.category.name}"),
                ui.Separator(),
                ui.TextDisplay(
                    f"**<:white_check_mark:983576747381518396> -- Available**\n"
                    f"{self.channel_string(self.available)}\n"
                ),
                ui.TextDisplay(
                    f"**<:x:983576786447245312> -- Unavailable**\n"
                    f"{self.channel_string(self.unavailable)}\n"
                ),
                ui.TextDisplay(
                    f"\n-# Last updated <t:{int(datetime.now(timezone.utc).timestamp())}:R>"
                )
            )
        ]

        try:
            await dashboard_message.edit(view=self, content=None)
        except Exception as e:
            pass

    def setup_channels(self):
        container = self.dashboard._message.components[0]
        available = container.components[2].content.split("\n")
        unavailable = container.components[3].content.split("\n")
        
        def get_channels(str_list):
            channels = []

            def strip_field(str) -> int:
                if str.replace(" ", "") == ZWSP3.replace(" ", "") or str == "":
                    return None
                return int(str.replace("\u200b", "").replace("<#", "").replace(">",""))
            
            for i, str in enumerate(str_list):
                if i == 0:
                    continue
                if (channel_id := strip_field(str)) and (channel := self.dashboard._bot.get_channel(channel_id)):
                    channels.append(channel)

            return channels

        self.available = get_channels(available)
        self.unavailable = get_channels(unavailable)

    def channel_string(self, channels: []):
        if channels:
            sorted_channels = [
                c for c in sorted(
                    filter(None, channels),
                    key=lambda c: c.position
                    )
            ]

            return "\n".join(
                [f"{c.mention}" for c in sorted_channels]
            )
        return ZWSP3


    def __init__(self, dashboard: "CategoryDashboard"):
        self.dashboard = dashboard

        super().__init__(
            ui.TextDisplay("Loading...."),
            store=False
        )
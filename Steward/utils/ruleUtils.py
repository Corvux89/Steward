from typing import TYPE_CHECKING
from Steward.models.automation.context import AutomationContext
from Steward.models.objects.servers import Server

if TYPE_CHECKING:
    from Steward.bot import StewardContext, StewardBot
    from Steward.models.objects.rules import StewardRule

async def execute_rules_for_trigger(
    bot: "StewardBot",
    server: Server,
    trigger: str,
    **extra_context
) -> list[dict]:    
    from Steward.models.objects.rules import StewardRule
    
    rules = await StewardRule.get_rules_for_trigger(bot.db, server.id, trigger)
    
    context = AutomationContext(
        server=server,
        **extra_context
    )
    
    results = []
    for rule in rules:
        if rule.evaluate_condition(context):
            result = await rule.execute_action(bot, context)
            results.append({"rule": rule.name, **result})
    
    return results
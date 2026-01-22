import json
import os

DEBUG = os.environ.get('DEBUG', False)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DEFAULT_PREFIX = os.environ.get("COMMAND_PREFIX", ".")
ERROR_CHANNEL = os.environ.get("ERROR_CHANNEL")
BOT_OWNERS = (json.loads(os.environ["BOT_OWNERS"]) if "BOT_OWNERS" in os.environ else None)
ADMIN_GUILDS = (
    json.loads(os.environ["ADMIN_GUILDS"]) if "ADMIN_GUILDS" in os.environ else None
)

DB_URL = os.environ.get("DATABASE_URL", "")

# Symbols
CHANNEL_BREAK = "```\n​ \n```"
ZWSP3 = "\u200b \u200b \u200b "
APPROVAL_EMOJI = ["✅", "greencheck"]
DENIED_EMOJI = ["❌"]
NULL_EMOJI = ["◀️", "⏪"]
EDIT_EMOJI = ["✏️", "📝"]


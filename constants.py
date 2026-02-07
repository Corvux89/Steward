import json
import os
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

DEBUG = os.environ.get('DEBUG', False)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DEFAULT_PREFIX = os.environ.get("COMMAND_PREFIX", ".")
ERROR_CHANNEL = os.environ.get("ERROR_CHANNEL")
BOT_OWNERS = (json.loads(os.environ["BOT_OWNERS"]) if "BOT_OWNERS" in os.environ else None)
ADMIN_GUILDS = (
    json.loads(os.environ["ADMIN_GUILDS"]) if "ADMIN_GUILDS" in os.environ else None
)

# all this to keep the dynamic url from heroku
def normalize_database_url(url: str) -> str:
    if not url:
        return url

    parsed = urlparse(url)
    if parsed.scheme in {"postgres", "postgresql"}:
        parsed = parsed._replace(scheme="postgresql+asyncpg")

    return urlunparse(parsed)


DB_URL = normalize_database_url(os.environ.get("DATABASE_URL", ""))

# Symbols
CHANNEL_BREAK = "```\n​ \n```"
ZWSP3 = "\u200b \u200b \u200b "
APPROVAL_EMOJI = ["✅", "greencheck"]
DENIED_EMOJI = ["❌"]
NULL_EMOJI = ["◀️", "⏪"]
EDIT_EMOJI = ["✏️", "📝"]


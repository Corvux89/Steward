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

    def normalize_sslmode_value(value: str | None) -> str | None:
        if value is None:
            return None
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return "require"
        if lowered in {"false", "0", "no", "off"}:
            return "disable"
        return value

    parsed = urlparse(url)
    is_plain_postgres = parsed.scheme in {"postgres", "postgresql"}
    if is_plain_postgres:
        parsed = parsed._replace(scheme="postgresql+asyncpg")

    query = dict(parse_qsl(parsed.query))
    sslmode = normalize_sslmode_value(query.pop("sslmode", None))
    if "ssl" not in query:
        if sslmode == "disable":
            query["ssl"] = "false"
        elif sslmode is not None:
            query["ssl"] = "true"
        elif is_plain_postgres:
            query.setdefault("ssl", "true")

    if sslmode is not None:
        query["sslmode"] = sslmode

    parsed = parsed._replace(query=urlencode(query))

    return urlunparse(parsed)


if "PGSSLMODE" in os.environ:
    normalized_sslmode = None
    try:
        normalized_sslmode = normalize_database_url("postgres://x:y@z/db?sslmode=" + os.environ["PGSSLMODE"]).split("sslmode=")[-1]
    except Exception:
        normalized_sslmode = None
    if normalized_sslmode:
        os.environ["PGSSLMODE"] = normalized_sslmode


DB_URL = normalize_database_url(os.environ.get("DATABASE_URL", ""))

# Symbols
CHANNEL_BREAK = "```\n​ \n```"
ZWSP3 = "\u200b \u200b \u200b "
APPROVAL_EMOJI = ["✅", "greencheck"]
DENIED_EMOJI = ["❌"]
NULL_EMOJI = ["◀️", "⏪"]
EDIT_EMOJI = ["✏️", "📝"]


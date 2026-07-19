import os
from dataclasses import dataclass


@dataclass
class Config:
    bot_token: str
    db_path: str = "bot.sqlite3"
    cf_api_token: str | None = None
    cf_account_id: str | None = None
    tavily_api_key: str | None = None
    enable_shell: bool = False
    enable_open_apps: bool = False
    allowed_apps: list[str] | None = None
    allowed_dirs: list[str] | None = None
    debug_intents: bool = False


def load_config() -> Config:
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN is not set in environment")
    db_path = os.getenv("DB_PATH", "bot.sqlite3")
    cf_api_token = os.getenv("CF_API_TOKEN")
    cf_account_id = os.getenv("CF_ACCOUNT_ID")
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    enable_shell = os.getenv("ENABLE_SHELL", "false").lower() == "true"
    enable_open_apps = os.getenv("ENABLE_OPEN_APPS", "false").lower() == "true"
    # Parse comma-separated allowed apps
    allowed_apps_env = os.getenv("ALLOWED_APPS", "")
    allowed_apps = [a.strip() for a in allowed_apps_env.split(",") if a.strip()] or None
    # Parse path list for allowed dirs; support both ; and : as separators
    allowed_dirs_env = os.getenv("ALLOWED_DIRS", "")
    sep = ";" if ";" in allowed_dirs_env else ":"
    allowed_dirs = [p.strip() for p in allowed_dirs_env.split(sep) if p.strip()] or None
    debug_intents = os.getenv("DEBUG_INTENTS", "false").lower() == "true"
    return Config(
        bot_token=token,
        db_path=db_path,
        cf_api_token=cf_api_token,
        cf_account_id=cf_account_id,
        tavily_api_key=tavily_api_key,
        enable_shell=enable_shell,
        enable_open_apps=enable_open_apps,
        allowed_apps=allowed_apps,
        allowed_dirs=allowed_dirs,
        debug_intents=debug_intents,
    )

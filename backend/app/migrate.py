"""Applies Alembic migrations on startup (idempotent), so every deploy upgrades the schema safely."""
from alembic import command
from alembic.config import Config

from app.config import BACKEND_DIR, settings


def upgrade() -> None:
    if settings.database_url.startswith("sqlite"):
        (BACKEND_DIR / "data").mkdir(exist_ok=True)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(cfg, "head")

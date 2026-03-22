"""Server configuration settings."""
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'game.db'}"
    DATA_DIR: Path = BASE_DIR / "data"
    MOB_RESPAWN_SECONDS: int = 60
    COMBAT_TURN_TIMEOUT_SECONDS: int = 30
    MAX_PLAYERS_PER_ROOM: int = 30

settings = Settings()

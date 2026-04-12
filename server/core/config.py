"""Server configuration settings."""
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # --- Player Defaults ---
    # Player defaults: applied at registration only. Changing these does NOT
    # retroactively update existing players in the database.
    DEFAULT_BASE_HP: int = 100
    DEFAULT_ATTACK: int = 10
    DEFAULT_STAT_VALUE: int = 1

    # --- Game Structure ---
    DEFAULT_SPAWN_ROOM: str = "town_square"
    STAT_CAP: int = 10
    LEVEL_UP_STAT_CHOICES: int = 3

    # --- Combat ---
    COMBAT_HAND_SIZE: int = 5
    COMBAT_MIN_DAMAGE: int = 1
    COMBAT_STARTING_ENERGY: int = 3
    COMBAT_ENERGY_REGEN: int = 3
    COMBAT_TURN_TIMEOUT_SECONDS: int = 30

    # --- NPC ---
    NPC_DEFAULT_HP_MULTIPLIER: int = 10
    NPC_ATTACK_DICE_MULTIPLIER: int = 2
    MOB_RESPAWN_SECONDS: int = 60
    RARE_CHECK_INTERVAL_SECONDS: int = 60

    # --- Auth ---
    MIN_USERNAME_LENGTH: int = 3
    MIN_PASSWORD_LENGTH: int = 6

    # --- XP & Stats ---
    CON_HP_PER_POINT: int = 5
    # >= 1.0 for stat=1 to produce a non-zero bonus; values < 1.0 are valid
    # but mean new characters (all stats=1) get no stat bonuses until level-up.
    STAT_SCALING_FACTOR: float = 1.0
    XP_CURVE_TYPE: str = "quadratic"
    XP_CURVE_MULTIPLIER: int = 25
    XP_CHA_BONUS_PER_POINT: float = 0.03
    XP_LEVEL_THRESHOLD_MULTIPLIER: int = 1000
    XP_EXPLORATION_REWARD: int = 50
    XP_INTERACTION_REWARD: int = 25
    XP_QUEST_REWARD: int = 100
    XP_PARTY_BONUS_PERCENT: int = 10

    # --- Trade ---
    TRADE_COOLDOWN_SECONDS: int = 5
    TRADE_SESSION_TIMEOUT_SECONDS: int = 60
    TRADE_REQUEST_TIMEOUT_SECONDS: int = 30
    MAX_TRADE_ITEMS: int = 10

    # --- Party ---
    MAX_PARTY_SIZE: int = 4
    PARTY_INVITE_TIMEOUT_SECONDS: int = 30
    PARTY_INVITE_COOLDOWN_SECONDS: int = 10

    # --- Chat ---
    MAX_CHAT_MESSAGE_LENGTH: int = 500
    CHAT_FORMAT: str = "markdown"

    # --- Room ---
    MAX_PLAYERS_PER_ROOM: int = 30

    # --- Admin ---
    ADMIN_SECRET: str = ""

    # --- Heartbeat ---
    HEARTBEAT_INTERVAL_SECONDS: int = 30
    HEARTBEAT_TIMEOUT_SECONDS: int = 10

    # --- Session Tokens ---
    SESSION_TOKEN_TTL_SECONDS: int = 300

    # --- Disconnect Grace Period ---
    DISCONNECT_GRACE_SECONDS: int = 120

    # --- Database ---
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'game.db'}"
    DATA_DIR: Path = BASE_DIR / "data"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_PRE_PING: bool = True

    # --- Migration ---
    @property
    def ALEMBIC_DATABASE_URL(self) -> str:
        """Auto-derived: strip async driver for sync Alembic usage."""
        url = self.DATABASE_URL
        url = url.replace("sqlite+aiosqlite", "sqlite")
        url = url.replace("postgresql+asyncpg", "postgresql")
        return url

    # --- Validators ---
    @field_validator("DEFAULT_BASE_HP")
    @classmethod
    def validate_base_hp(cls, v: int) -> int:
        if v < 1:
            raise ValueError("DEFAULT_BASE_HP must be >= 1")
        return v

    @field_validator("COMBAT_HAND_SIZE")
    @classmethod
    def validate_hand_size(cls, v: int) -> int:
        if v < 1:
            raise ValueError("COMBAT_HAND_SIZE must be >= 1")
        return v

    @field_validator("COMBAT_MIN_DAMAGE")
    @classmethod
    def validate_min_damage(cls, v: int) -> int:
        if v < 0:
            raise ValueError("COMBAT_MIN_DAMAGE must be >= 0")
        return v

    @field_validator("STAT_CAP")
    @classmethod
    def validate_stat_cap(cls, v: int) -> int:
        if v < 1:
            raise ValueError("STAT_CAP must be >= 1")
        return v

    @field_validator("LEVEL_UP_STAT_CHOICES")
    @classmethod
    def validate_level_up_choices(cls, v: int) -> int:
        if v < 1:
            raise ValueError("LEVEL_UP_STAT_CHOICES must be >= 1")
        return v

    @field_validator("DB_POOL_SIZE")
    @classmethod
    def validate_pool_size(cls, v: int) -> int:
        if v < 1:
            raise ValueError("DB_POOL_SIZE must be >= 1")
        return v

settings = Settings()

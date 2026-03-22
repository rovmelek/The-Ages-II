# Story 1.1: Project Scaffolding & Configuration

Status: done

## Story

As a developer,
I want the project directory structure, dependencies, and configuration in place,
So that all future stories have a consistent foundation to build on.

## Acceptance Criteria

1. The domain-driven directory structure exists under `server/` with packages: `core/`, `core/effects/`, `net/`, `net/handlers/`, `player/`, `room/`, `room/objects/`, `combat/`, `combat/cards/`, `items/`, `web/`
2. `pyproject.toml` defines all production and dev dependencies with correct minimum versions
3. `run.py` starts the server via uvicorn using settings from `server/core/config.py`
4. `server/core/config.py` provides Pydantic `BaseSettings` with: HOST, PORT, DEBUG, DATABASE_URL, DATA_DIR, MOB_RESPAWN_SECONDS, COMBAT_TURN_TIMEOUT_SECONDS, MAX_PLAYERS_PER_ROOM
5. All `__init__.py` files exist for every Python package
6. Data directories exist: `data/rooms/`, `data/cards/`, `data/items/`, `data/npcs/`
7. `tests/` directory exists with `__init__.py`
8. `pip install -e ".[dev]"` succeeds without errors

## Tasks / Subtasks

- [x] Task 1: Create directory structure (AC: #1, #6, #7)
  - [x] Create all `server/` subdirectories matching architecture spec
  - [x] Create all `data/` subdirectories
  - [x] Create `tests/` directory
  - [x] Create `__init__.py` in every Python package (AC: #5)
- [x] Task 2: Create `pyproject.toml` (AC: #2)
  - [x] Define project metadata (name, version, description, requires-python)
  - [x] Add all production dependencies with minimum versions
  - [x] Add dev dependencies under `[project.optional-dependencies]`
  - [x] Add build-system configuration
- [x] Task 3: Create `server/core/config.py` (AC: #4)
  - [x] Implement `Settings` class with Pydantic BaseSettings
  - [x] Define all settings with defaults
  - [x] Export module-level `settings` singleton
- [x] Task 4: Create `run.py` (AC: #3)
  - [x] Import settings from `server.core.config`
  - [x] Launch uvicorn with host, port, reload from settings
- [x] Task 5: Verify installation (AC: #8)
  - [x] Run `pip install -e ".[dev]"` and confirm success (requires `.venv`)

## Dev Notes

### Architecture Compliance

This story creates the **revised domain-driven structure** from `architecture.md`, NOT the flat structure from the original `THE_AGES_SERVER_PLAN.md`. Key differences:

| Original Plan | Revised Architecture |
|--------------|---------------------|
| `server/config.py` | `server/core/config.py` |
| `server/models/` (all models together) | Models split per domain: `player/models.py`, `room/models.py`, etc. |
| `server/game/` (all game logic) | Split: `room/`, `combat/`, `items/` |
| `server/persistence/` | Repos in domain folders: `player/repo.py`, `room/repo.py` |

### Directory Structure (Exact)

```
the-ages-ii/                    # project root (already exists as git repo)
├── server/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── effects/
│   │       └── __init__.py
│   ├── net/
│   │   ├── __init__.py
│   │   └── handlers/
│   │       └── __init__.py
│   ├── player/
│   │   └── __init__.py
│   ├── room/
│   │   ├── __init__.py
│   │   └── objects/
│   │       └── __init__.py
│   ├── combat/
│   │   ├── __init__.py
│   │   └── cards/
│   │       └── __init__.py
│   ├── items/
│   │   └── __init__.py
│   └── web/
│       └── __init__.py
├── data/
│   ├── rooms/
│   ├── cards/
│   ├── items/
│   └── npcs/
├── tests/
│   └── __init__.py
├── pyproject.toml
└── run.py
```

### pyproject.toml Specification

```toml
[project]
name = "the-ages-server"
version = "0.1.0"
description = "The Ages II - Multiplayer dungeon game server"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "aiosqlite>=0.19.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "bcrypt>=4.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

**Critical**: `pydantic-settings` is a separate package from `pydantic`. The original plan noted this but didn't include it in the dependencies list. It MUST be included.

### config.py Specification

```python
"""Server configuration settings."""
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # server/core/config.py -> project root

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
```

**Critical path difference**: Because config.py is now at `server/core/config.py` (2 levels deep instead of 1), `BASE_DIR` must use `.parent.parent.parent` (3 parents) to reach the project root. The original plan used `.parent.parent` because config was at `server/config.py`.

### run.py Specification

```python
"""Entry point: launch the game server with uvicorn."""
import uvicorn
from server.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "server.app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
```

**Note**: `server.app:app` won't exist until Story 1.8 (Game Orchestrator). That's expected — `run.py` is created now but won't be runnable until the app module exists.

### Anti-Patterns to Avoid

- **DO NOT** create `server/app.py` yet — that's Story 1.8
- **DO NOT** create any database models yet — that's Story 1.2
- **DO NOT** create a flat `server/models/` or `server/game/` directory — use the domain-driven structure
- **DO NOT** put config at `server/config.py` — it goes at `server/core/config.py`
- **DO NOT** add any `.gitkeep` files in data directories — just create the directories
- **DO NOT** create any empty placeholder files beyond `__init__.py` — each file is created by the story that needs it

### Project Structure Notes

- All paths are relative to project root `/home/hytseng/github/The-Ages-II/`
- The project root already exists as a git repository
- BMAD framework files (`_bmad/`, `.claude/`, etc.) already exist — do not modify them
- `data/` directories are empty for now — sample data comes in Epic 6

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#3.1 Directory Structure]
- [Source: _bmad-output/planning-artifacts/architecture.md#12. Tech Stack]
- [Source: THE_AGES_SERVER_PLAN.md#Step 1: Project Scaffolding]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.1]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
None

### Completion Notes List
- Fixed `build-backend` in pyproject.toml: `setuptools.backends._legacy:_Backend` → `setuptools.build_meta` (original spec had invalid backend)
- Added `[tool.setuptools.packages.find]` with `include = ["server*"]` to prevent `data/` from being detected as a Python package
- Virtual environment (`.venv`) required for installation due to PEP 668 on Ubuntu — not a project issue, just a system config requirement

### File List
- `pyproject.toml` — project metadata and dependencies
- `run.py` — server entry point
- `server/__init__.py`
- `server/core/__init__.py`
- `server/core/config.py` — Pydantic BaseSettings
- `server/core/effects/__init__.py`
- `server/net/__init__.py`
- `server/net/handlers/__init__.py`
- `server/player/__init__.py`
- `server/room/__init__.py`
- `server/room/objects/__init__.py`
- `server/combat/__init__.py`
- `server/combat/cards/__init__.py`
- `server/items/__init__.py`
- `server/web/__init__.py`
- `tests/__init__.py`
- `data/rooms/` (empty directory)
- `data/cards/` (empty directory)
- `data/items/` (empty directory)
- `data/npcs/` (empty directory)

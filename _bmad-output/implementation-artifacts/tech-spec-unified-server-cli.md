---
title: 'Unified Server CLI'
slug: 'unified-server-cli'
created: '2026-04-08'
status: 'implementation-complete'
stepsCompleted: [1, 2, 3, 4]
tech_stack: ['python 3.11+', 'argparse (stdlib)', 'subprocess/os/signal/urllib/importlib.metadata (stdlib)', 'uvicorn']
files_to_modify: ['server/cli.py (new)', 'pyproject.toml', '.gitignore', 'tests/test_cli.py (new)']
code_patterns: ['from __future__ import annotations first', 'console_scripts entry point', 'subprocess.Popen daemon', 'PID file + ps identity check', 'file-based logging', 'BASE_DIR computed inline']
test_patterns: ['sync tests (no async)', 'unittest.mock.patch for subprocess/os', 'monkeypatch for config', 'descriptive docstrings on every test', 'flat tests/ directory']
---

# Tech-Spec: Unified Server CLI

**Created:** 2026-04-08

## Overview

### Problem Statement

Server control is fragmented across three mechanisms: `python run.py` (start), `Ctrl+C` (stop), and `curl` admin API endpoints (restart/shutdown with ADMIN_SECRET). There is no single tool to manage the server lifecycle.

### Solution

Create an `ages-server` console entry point (via pyproject.toml `[project.scripts]`) that provides `start`, `stop`, `restart`, `status`, and `logs` subcommands. The `start` command daemonizes the server process (or runs in foreground with `--foreground`), writes logs to files, and tracks the PID for other subcommands to use.

### Scope

**In Scope:**
- `ages-server start` — daemonize server (or `--foreground`), write logs to `logs/` directory, write PID to `data/server.pid`
- `ages-server stop` — read PID file, send SIGTERM, clean up PID file
- `ages-server restart` — stop then start (preserves params)
- `ages-server status` — check PID file + process liveness + health endpoint
- `ages-server logs` — tail server log file (read path from PID file)
- `[project.scripts]` entry in pyproject.toml
- File-based logging configuration

**Out of Scope:**
- Modifying existing admin REST API
- Web client changes
- CLI configuration file
- Windows support (signals/daemon are POSIX)
- Multi-instance support (single PID file = single instance)
- Auto-restart on crash (use systemctl/pm2 for that)

## Context for Development

### Codebase Patterns

- Entry point today: `run.py` calls `uvicorn.run()` with settings from `server.core.config.Settings`
- Settings: Pydantic `BaseSettings` in `server/core/config.py` — `HOST`, `PORT`, `DEBUG`
- Admin shutdown: `os.kill(os.getpid(), signal.SIGTERM)` after `game.shutdown()`
- Admin restart: `os.execv(sys.executable, ...)` after `game.shutdown()`
- No existing PID file or log file infrastructure

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `run.py` | Current entry point — uvicorn launcher |
| `server/app.py` | FastAPI app, `Game` class, lifespan manager |
| `server/core/config.py` | `Settings` (HOST, PORT, DEBUG, etc.) |
| `server/net/handlers/admin.py` | Admin shutdown/restart via REST |
| `pyproject.toml` | Package config — needs `[project.scripts]` |

### Technical Decisions (ADRs)

**ADR-1: Daemon Mechanism** — `subprocess.Popen` with `start_new_session=True`
- Alternatives considered: `os.fork()` double-fork (too complex), `multiprocessing.Process` (not a true daemon)
- Rationale: Simplest correct approach — spawns uvicorn as fully detached child, redirects stdout/stderr to log files, writes child PID, CLI exits immediately. No extra deps.

**ADR-2: PID Tracking** — Track the uvicorn child process PID (not a wrapper/supervisor)
- Alternatives considered: CLI stays resident as supervisor (adds complexity, two processes)
- Rationale: Uvicorn already handles SIGTERM gracefully via FastAPI lifespan → `game.shutdown()`. Direct control, no supervisor layer needed.

**ADR-3: Log Strategy** — Simple append to `logs/server.log`, customizable via `--log-file` flag
- Alternatives considered: `RotatingFileHandler` (more setup), external `logrotate` (overkill)
- Rationale: YAGNI for dev/staging. Single file is sufficient; rotation can be added later.

**ADR-4: Status Check** — PID check (`os.kill(pid, 0)`) + HTTP `/health` endpoint check
- Alternatives considered: PID only (misses stuck server), HTTP only (requires network)
- Rationale: A stuck server with valid PID is a real failure mode. Both signals give actionable info.

**ADR-5: Stop Timeout** — SIGTERM + 10s default timeout + `--force` flag for SIGKILL
- Alternatives considered: Always SIGKILL after timeout (skips graceful shutdown), error-only (server could hang)
- Rationale: Player state persistence during shutdown is a key feature (Epic 7). Force-killing by default would silently lose data. `--force` provides an escape hatch for hung processes.

**ADR-6: `run.py` preserved** — Keep `run.py` as legacy foreground entry point. CLI now provides `--foreground` flag (ADR-20) which supersedes `run.py` for foreground use with `--host`/`--port` support

**ADR-7: PID file location** — `data/server.pid` (`data/` already exists and is gitignored)

**ADR-8: No new dependencies** — stdlib only (`argparse`, `subprocess`, `os`, `signal`, `urllib`)

**ADR-9: Process Identity Verification** — `subprocess.run(["ps", "-p", str(pid), "-o", "command="])` checking for `uvicorn` in output
- Alternatives considered: No identity check (Razor cut — PID reuse risk accepted), process start time comparison (more complex)
- Rationale: PID reuse is rare but sending SIGTERM to an innocent process is unacceptable. `ps` check is 3 lines, works on both Linux and macOS (`command=` shows full command line on both). Restored after adversarial review flagged F1/F26 as Critical.
- **Fallback**: If `ps` subprocess fails (`FileNotFoundError`, non-zero exit), skip identity check and proceed with liveness-only. Log a warning: "Warning: could not verify process identity (ps not available)". Do NOT crash the CLI because `ps` is missing.

**ADR-10: Uvicorn Launch Command** — `[sys.executable, "-m", "uvicorn", "server.app:app", "--host", host, "--port", str(port)]`
- Alternatives considered: `python run.py` (can't override host/port, DEBUG enables reload which breaks PID tracking), inline `-c` (ugly)
- Rationale: Clean, explicit args, no dependency on `run.py`. Avoids DEBUG reload mode which is incompatible with daemon PID tracking.

**ADR-11: PID File Format** — Multi-line: PID, host, port, log_path (4 lines)
- Alternatives considered: PID-only (status can't find correct health endpoint after `--port` override), separate metadata file (another file to manage)
- Rationale: If started with `--port 9000`, status needs to hit port 9000 not default 8000. Log path stored so `ages-server logs` works even with custom `--log-file`. Four lines, read with `splitlines()`, trivial parsing.

**ADR-12: Log Merging** — `stderr=subprocess.STDOUT` to single file
- Alternatives considered: Separate stdout/stderr files (uvicorn logs to stderr by default, so `server.log` would be empty — confusing)
- Rationale: One chronological log stream. One file to `tail -f`.

**ADR-13: Startup Verification** — Poll `os.kill(pid, 0)` every 0.5s for 3s (6 checks)
- Alternatives considered: Single check after `sleep(2)` (misses failures at 2.5s), health endpoint wait (too slow, couples to server init time)
- Rationale: Returns immediately on failure detection. 6 lines of code for meaningful UX improvement over blind sleep.

**ADR-14: Health Check in Status** — `urllib.request.urlopen(url, timeout=3)` with JSON parse
- Alternatives considered: `subprocess.run(["curl", ...])` (external dep), raw `socket.connect` (only checks port, not HTTP response)
- Rationale: Stdlib, verifies actual `{"status": "ok"}` response, not just port open. 5 lines with error handling.

**ADR-15: Stop Wait Mechanism** — Poll `os.kill(pid, 0)` every 0.5s for 10s (20 checks)
- Alternatives considered: `os.waitpid()` (fails with ECHILD — server is not a child of the `stop` CLI process)
- Rationale: `waitpid` only works for child processes. The server was spawned by a previous CLI invocation. Polling is the only option.

**ADR-16: Default Host/Port Resolution** — Argparse defaults are `None`, resolve at runtime via deferred `settings` import
- Alternatives considered: Import `Settings` at module level (triggers Pydantic init — can fail on malformed env vars), hardcode defaults (duplicates, diverges)
- Rationale: `host = args.host or settings.HOST`, `port = args.port or settings.PORT`. Import `settings` only inside `cmd_start()`. `BASE_DIR` computed inline in `cli.py` as `Path(__file__).resolve().parent.parent` — NOT imported from `config.py` (which triggers `Settings()` instantiation at module level). Follows project pattern of deferred imports.

**ADR-18: BASE_DIR Inline Computation** — `BASE_DIR = Path(__file__).resolve().parent.parent` in `cli.py`
- Alternatives considered: Import from `server.core.config` (triggers `Settings()` init at import time — adversarial review F31), move `BASE_DIR` to separate module (unnecessary refactor)
- Rationale: `cli.py` lives at `server/cli.py`. Two `.parent` calls reach the project root. Same result as `config.py`'s `BASE_DIR` without importing the module. Zero side effects for `--help`/`--version`.

**ADR-19: Logs Subcommand** — `ages-server logs [--follow] [--lines N]` wrapping `tail`
- Alternatives considered: No logs command (users must remember `tail -f`), reading from hardcoded path (wrong if `--log-file` used)
- Rationale: Every comparable tool (systemctl, docker, pm2, supervisord) provides built-in log viewing. High UX value, ~10 lines. Log path read from PID file (4th line) so it works correctly even with custom `--log-file`.

**ADR-20: Foreground Flag** — `ages-server start --foreground` runs uvicorn in-process (no daemon)
- Alternatives considered: Use `run.py` for foreground (doesn't accept `--host`/`--port`), update `run.py` (separate entry point, confusing)
- Rationale: One tool for everything. `--foreground` calls `uvicorn.run()` directly instead of Popen. No PID file, no log redirect, Ctrl+C works. ~5 lines.

**ADR-17: Version String** — `importlib.metadata.version("the-ages-server")`
- Alternatives considered: Parse `pyproject.toml` (needs `tomllib`), hardcode (two places to update)
- Rationale: Stdlib since 3.8, always matches pyproject.toml. CLI requires `pip install -e .` anyway for the console script.

## Implementation Plan

### Tasks

- [x] **Task 1: Register console entry point**
  - File: `pyproject.toml`
  - Action: Add `[project.scripts]` section: `ages-server = "server.cli:main"`
  - Note: User must re-run `pip install -e .` to register the command

- [x] **Task 2: Update .gitignore**
  - File: `.gitignore`
  - Action: Add `logs/` and `data/server.pid` entries

- [x] **Task 3: Create `server/cli.py`**
- File: `server/cli.py`
- Action: Create CLI module with argparse subcommands
- Subcommands:
  - `start [--host HOST] [--port PORT] [--log-file PATH] [--foreground]`: If `--foreground` and `--log-file` both provided, print "Error: --log-file cannot be used with --foreground" and `sys.exit(1)`. If `--foreground`, import `uvicorn` and call `uvicorn.run("server.app:app", host=host, port=port)` directly — no daemon, no PID file, no log redirect, Ctrl+C works. Otherwise (daemon mode): Create `logs/` directory if needed (`os.makedirs(exist_ok=True)`). Open log file in append mode (`log_fd = open(log_path, "a")`). Launch uvicorn via `[sys.executable, "-m", "uvicorn", "server.app:app", ...]` as daemon subprocess with `start_new_session=True`, `stdout=log_fd`, `stderr=subprocess.STDOUT`, `cwd=BASE_DIR` so the CLI works from any directory. Close `log_fd` in the CLI after Popen (child inherits the FD). All paths (PID file, log file, log dir) resolved relative to `BASE_DIR`. Optional `--host`/`--port` override `Settings` defaults. Write multi-line PID file (`{BASE_DIR}/data/server.pid`: pid, host, port, log_path — 4 lines) immediately after Popen. Refuse if already running — check PID file + `os.kill(pid, 0)` liveness + verify process identity via `subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True)` checking for `uvicorn` in output. If PID alive but identity mismatch, treat as stale (PID was recycled). Clean up stale PID files automatically. Poll child every 0.5s for 3s to verify startup — on failure, print last 10 lines of log and exit with error.
  - `stop [--force]`: Read multi-line PID file (try/except for malformed — treat as stale). Verify process identity via `ps -p PID -o command=` — if PID alive but not uvicorn, treat as stale (PID recycled, do NOT send signal). Wrap entire stop logic in `try/finally` to ensure PID file cleanup even if CLI is interrupted (Ctrl+C). Send `SIGTERM`, poll `os.kill(pid, 0)` every 0.5s for 10s until dead. `--force` flag shortens SIGTERM wait to 3s then sends SIGKILL — print warning BEFORE sending: "Warning: --force will kill the server without saving player state. Proceeding...". Remove PID file idempotently (`try/except FileNotFoundError`). Clean up stale PID file if process is already dead.
  - `restart [--force] [--host HOST] [--port PORT] [--log-file PATH]`: If PID file exists, read host/port from it as defaults for the new start (so restart preserves original params unless overridden by flags). Call stop (passing `--force` if provided). If stop fails (exception), abort restart — do NOT start a second instance. If stop reports "not running" (no PID file or stale), proceed to start anyway (treat as fresh start). After successful stop, `time.sleep(1)` for port release, then start (using flag overrides if provided, else preserved params from PID file, else Settings defaults).
  - `status`: Read multi-line PID file (pid, host, port). Check process alive (`os.kill(pid, 0)`) — handle `PermissionError` separately from `ProcessLookupError` ("Server may be running as a different user (PID {pid})"). Verify identity via `ps`. If alive and verified, hit `http://{host}:{port}/health` via `urllib.request.urlopen(timeout=3)`, parse JSON response. Health states: "healthy" (200 + `{"status": "ok"}`), "unhealthy" (200 but unexpected response body), "unreachable" (connection refused / timeout / non-200).
  - `logs [--follow] [--lines N]`: Read log path from PID file (4th line). If no PID file, use default `{BASE_DIR}/logs/server.log`. Execute `subprocess.run(["tail", "-n", str(lines), log_path])` (default lines=50). If `--follow`, use `["tail", "-f", "-n", str(lines), log_path]` — this replaces the CLI process via `os.execvp` so Ctrl+C goes directly to `tail`. If log file doesn't exist, print "No log file found at {path}" and `sys.exit(1)`.
- Global flags: `--version` via `importlib.metadata.version("the-ages-server")` (catch `PackageNotFoundError` → "unknown")
- **BASE_DIR computed inline** (NOT imported from `server.core.config`): `BASE_DIR = Path(__file__).resolve().parent.parent` — this avoids importing `config.py` at module level, which would trigger `settings = Settings()` Pydantic init and could fail on malformed env vars during `--help`/`--version`. The `server.core.config.BASE_DIR` equivalent is `Path(__file__).resolve().parent.parent.parent` (from config.py's perspective, 3 levels up); from `server/cli.py`, it's 2 levels up.
- **Windows guard**: At the top of `main()`, check `sys.platform != "win32"` — if Windows, print "This command requires a POSIX system (Linux/macOS)" and `sys.exit(1)`
- Default resolution: Argparse defaults are `None`. Inside `cmd_start()`: `from server.core.config import settings` (deferred) then `host = args.host or settings.HOST`
- Path resolution: `--log-file` resolved to absolute path via `Path(arg).resolve()` before use
- Entry function: `def main() -> None`

- [x] **Task 4: Add tests**
- File: `tests/test_cli.py`
- Test argument parsing for each subcommand
- Test PID file write/read/cleanup logic (multi-line format: pid, host, port, log_path)
- Test start refuses when already running (PID alive + identity match)
- Test start cleans up stale PID file (dead process)
- Test start cleans up recycled PID (alive but identity mismatch)
- Test start detects startup failure (child dies within verification window)
- Test stop with no PID file gives clean error (exit 0)
- Test stop cleans up stale PID file (process dead)
- Test stop with --force prints warning then sends SIGKILL
- Test stop handles PermissionError gracefully (different user)
- Test stop try/finally cleans PID on interrupt
- Test stop verifies identity before sending SIGTERM
- Test restart passes --force to stop
- Test restart preserves host/port from PID file
- Test restart when not running proceeds to start
- Test restart aborts if stop fails
- Test status dual-check (PID + identity + health endpoint)
- Test status shows "unhealthy" for unexpected health response
- Test status shows PermissionError message for different-user process
- Test --version prints package version
- Test --version prints "unknown" when not installed
- Test start --log-file custom path (resolved to absolute)
- Test start --host/--port override
- Test main() dispatches correct subcommand function
- Test no subcommand prints help
- Test Windows guard exits with message
- Test logs reads path from PID file
- Test logs falls back to default when no PID file
- Test logs --follow uses tail -f
- Test logs with missing file gives clean error
- Test start --foreground runs uvicorn.run directly (no Popen)
- Test PID file 4-line format (pid, host, port, log_path)
- Test ps fallback when ps not available (skip identity check, warn)
- Test --foreground + --log-file mutual exclusion error

### Acceptance Criteria

- [ ] **AC1: Start command daemonizes server with startup verification**
- Given: No server is running
- When: User runs `ages-server start`
- Then: Server process starts in background, multi-line PID file written to `data/server.pid` (pid, host, port, log_path), CLI polls child every 0.5s for 3s to verify startup, logs written to `logs/server.log`, CLI prints:
  ```
  Server started (PID 12345)
    Logs: /absolute/path/to/logs/server.log
    Listening on 0.0.0.0:8000

    View logs:  ages-server logs --follow
    Stop:       ages-server stop
  ```

**AC1a: Start detects and reports startup failure**
- Given: No server is running, but server will crash on startup (e.g., bad config, port in use)
- When: User runs `ages-server start`
- Then: CLI detects child death during 0.5s polling window, prints last 10 lines of log file, removes PID file, exits with non-zero code

- [ ] **AC2: Start refuses if already running (with identity check)**
- Given: Server is already running (valid PID file, process alive per `os.kill(pid, 0)`, `ps` confirms uvicorn)
- When: User runs `ages-server start`
- Then: CLI prints error message with PID and `sys.exit(1)`

- [ ] **AC2a: Start cleans up stale PID file (dead process)**
- Given: PID file exists but process is dead (`os.kill(pid, 0)` raises `ProcessLookupError`)
- When: User runs `ages-server start`
- Then: CLI removes stale PID file, warns user, proceeds with normal start

- [ ] **AC2b: Start cleans up recycled PID (identity mismatch)**
- Given: PID file exists, process is alive, but `ps` output does NOT contain `uvicorn`
- When: User runs `ages-server start`
- Then: CLI removes stale PID file, warns "PID was recycled by another process", proceeds with normal start

- [ ] **AC3: Stop command terminates server gracefully**
- Given: Server is running with PID in `data/server.pid`
- When: User runs `ages-server stop`
- Then: Server process receives SIGTERM, CLI waits up to 10s for exit, PID file is removed, CLI prints confirmation

**AC3a: Stop with --force kills hung server**
- Given: Server is running but not responding to SIGTERM
- When: User runs `ages-server stop --force`
- Then: SIGTERM sent, CLI waits only 3s (not 10s), if still alive sends SIGKILL, PID file is removed, CLI warns about ungraceful shutdown

**AC3b: Stop cleans up stale PID file**
- Given: PID file exists but process is dead
- When: User runs `ages-server stop`
- Then: CLI removes stale PID file, prints "Server is not running (stale PID file cleaned up)" and exits cleanly

- [ ] **AC4: Stop with no server gives clean error**
- Given: No PID file exists
- When: User runs `ages-server stop`
- Then: CLI prints "Server is not running" and `sys.exit(0)`

- [ ] **AC5: Restart cycles the server**
- Given: Server is running
- When: User runs `ages-server restart`
- Then: Server stops (preserving host/port from PID file as defaults), CLI sleeps 1s for port release, then starts again with new PID using preserved params

- [ ] **AC5a: Restart when server is not running**
- Given: No server is running (no PID file or stale PID)
- When: User runs `ages-server restart`
- Then: Stop reports "not running", restart proceeds to start the server normally

- [ ] **AC5b: Restart aborts if stop fails**
- Given: Server is running but stop fails (e.g., PermissionError)
- When: User runs `ages-server restart`
- Then: CLI prints stop error, does NOT start a second instance, `sys.exit(1)`

- [ ] **AC6: Status reports server state with dual check**
- Given: Server may or may not be running
- When: User runs `ages-server status`
- Then: CLI checks PID file + process liveness first, then hits `/health` endpoint if alive. Output format:
  ```
  Server is running (PID 12345)
    Health: healthy
    Listening on 0.0.0.0:8000
  ```
  or:
  ```
  Server is running (PID 12345)
    Health: unhealthy (unexpected response)
  ```
  or:
  ```
  Server is running (PID 12345)
    Health: unreachable (server may be starting up or stuck)
  ```
  or:
  ```
  Server may be running as a different user (PID 12345)
  ```
  or:
  ```
  Server is not running
  ```

- [ ] **AC7: Logs subcommand shows server logs**
- Given: Server was started (PID file exists with log path)
- When: User runs `ages-server logs`
- Then: CLI prints last 50 lines of the log file

- [ ] **AC7a: Logs subcommand with --follow**
- Given: Server is running
- When: User runs `ages-server logs --follow`
- Then: CLI tails the log file in real-time (Ctrl+C to stop)

- [ ] **AC7b: Logs subcommand with no log file**
- Given: No log file exists at the expected path
- When: User runs `ages-server logs`
- Then: CLI prints "No log file found at {path}" and `sys.exit(1)`

- [ ] **AC8: Start --foreground runs in foreground**
- Given: No server is running
- When: User runs `ages-server start --foreground`
- Then: Server runs in the foreground (no daemon, no PID file, no log redirect). Ctrl+C stops it. Logs print to terminal.

- [ ] **AC9: Logs are written to file (daemon mode)**
- Given: Server started via `ages-server start`
- When: Server processes requests
- Then: All uvicorn and application logs appear in `logs/server.log`

## Additional Context

### Dependencies

- No new Python packages required — stdlib only (`argparse`, `subprocess`, `os`, `signal`, `time`, `urllib`)
- Requires re-install: `pip install -e .` after adding console script

### Testing Strategy

- Unit tests: Mock subprocess/os calls, test CLI logic in isolation
- PID file lifecycle: Write, read, stale detection, cleanup
- No integration test that actually starts a server (too slow/flaky for unit tests)

### Error Handling

- **Permission denied** (PID file read/write, signal send): Catch `PermissionError`, print clear message — "Permission denied. Was the server started as a different user?"
- **PermissionError on liveness check**: `os.kill(pid, 0)` raises `PermissionError` if process exists but is owned by another user. Distinct from `ProcessLookupError` (dead). Print "Server may be running as a different user (PID {pid})" — do NOT treat as stale, do NOT send signals.
- **Stale PID**: Check `os.kill(pid, 0)` — if `ProcessLookupError`, process is dead. Clean up PID file and proceed.
- **PID reuse (recycled PID)**: After liveness check passes, verify process identity via `ps -p PID -o command=`. If output does NOT contain `uvicorn`, treat as stale — PID was recycled by the OS. Clean up PID file, warn user, proceed.
- **Malformed PID file**: Wrap PID file read in try/except (`IndexError`, `ValueError`). If malformed, treat as stale — delete and proceed.
- **Startup failure**: Poll child every 0.5s for 3s. If dead at any check, tail last 10 lines of log file and display immediately.
- **Port in use on restart**: `time.sleep(1)` after stop for port release. If start still fails, startup verification catches it and shows the log.
- **Version before install**: Catch `PackageNotFoundError` from `importlib.metadata.version()` — print "unknown (run `pip install -e .`)".
- **Concurrent stop**: PID file deletion wrapped in `try/except FileNotFoundError: pass` — idempotent.
- **Relative log path**: Resolve `--log-file` to absolute via `Path.resolve()` before use and display.
- **Wrong working directory**: All paths (PID file, log file, log dir) resolved relative to `BASE_DIR` (computed inline). Popen called with `cwd=BASE_DIR`. CLI works from any directory.
- **Ctrl+C during stop**: Wrap stop polling in `try/finally` to ensure PID file cleanup even if interrupted.
- **Restart stop failure**: If stop raises an exception, abort restart — do NOT start a second instance.
- **Windows**: Check `sys.platform` at top of `main()`. Print "This command requires a POSIX system" and `sys.exit(1)`.
- **No subcommand**: argparse prints help and exits. Specify `parser.set_defaults(func=None)` — if `func is None`, print help and `sys.exit(0)`.
- **`ps` not available**: If `subprocess.run(["ps", ...])` raises `FileNotFoundError` or returns non-zero, skip identity check, proceed with liveness-only, print warning.
- **`--foreground` + `--log-file`**: Mutually exclusive. Print "Error: --log-file cannot be used with --foreground" and `sys.exit(1)`.

### Risk Mitigations (Pre-mortem)

| Risk | Severity | Mitigation |
|------|----------|------------|
| Zombie PID file (crash/OOM) | High | `os.kill(pid, 0)` liveness check + `ps` identity check, auto-cleanup stale PIDs |
| PID reuse (OS recycles PID) | Critical | `ps -p PID -o command=` identity verification before any signal send |
| Silent startup death | High | Post-spawn verification + log tail on failure |
| Restart port TIME_WAIT | Low | `time.sleep(1)` between stop and start; startup verification catches failures |
| Malformed PID file | Low | Try/except on read, treat as stale |
| `--force` waits too long | Medium | Shorten SIGTERM wait to 3s when `--force` set |
| Concurrent stop race | Low | Idempotent PID file delete |
| Permission mismatch | Low | Clear error messages for PermissionError |
| Wrong working directory | High | All paths relative to `BASE_DIR` (computed inline), Popen `cwd=BASE_DIR` |
| BASE_DIR import side effect | Critical | Compute `BASE_DIR` inline in cli.py, NOT imported from config.py |
| Ctrl+C during stop | Medium | `try/finally` ensures PID cleanup |
| Restart stop failure | Medium | Abort restart if stop fails — never start a second instance |
| Log file growth | Low | Out of scope (ADR-3); document in --help |
| Single instance only | Low | Single PID file enforces one instance; multi-instance out of scope for v1 |

### Notes

- `run.py` remains as the foreground/debug entry point — `ages-server start` is for daemon mode
- On macOS (Darwin), `SIGTERM` is the standard graceful shutdown signal — matches existing admin endpoint behavior
- **Restart warning**: Restart interrupts active gameplay sessions (combat state is transient). Use `/admin/status` with `ADMIN_SECRET` to check active players before restarting in production
- **Exit codes**: `sys.exit(0)` for success, `sys.exit(1)` for all errors. No error-specific codes at this stage
- **Startup verification limit**: 3s polling window is a heuristic — server could crash at 3.1s. `ages-server status` is the safety net for post-startup health checks
- **PID file write format**: Exactly `f"{pid}\n{host}\n{port}\n{log_path}\n"` — 4 lines. Reads are defensive (try/except for malformed). Backward-compatible: if only 3 lines (old format), `logs` command falls back to default path.
- **CLI restart vs admin restart**: Intentionally different mechanisms. CLI: stop process + start new process (clean PID, fresh state). Admin API: `os.execv` (same process re-executes, inherits open FDs). CLI approach is cleaner for external management.
- **Single instance only**: One PID file = one server instance. Running two instances on different ports is not supported in v1. Explicitly out of scope.
- **Exit code clarification**: `sys.exit(0)` for: success, "server is not running" on stop (AC4), stale PID cleanup on stop (AC3b). `sys.exit(1)` for: all errors, "already running" on start (AC2), stop failures, startup failures.
- **No subcommand**: `ages-server` with no subcommand prints help and `sys.exit(0)`.
- **.gitignore strategy**: `data/` contains tracked JSON game data — only individual generated files (`data/game.db`, `data/server.pid`) are gitignored, not the entire directory.
- **Port release on restart**: Uvicorn sets `SO_REUSEADDR` by default, so TCP TIME_WAIT is generally not an issue. The 1s sleep is a safety margin. If start still fails, startup verification reports the error.
- **Log file open/close**: CLI opens log file (`open(path, "a")`), passes FD to Popen, then closes it immediately. Child process inherits the FD and continues writing. Open with `encoding="utf-8"` for consistency.
- **Test for main() dispatch**: Include a test that mocks `cmd_start`/`cmd_stop`/etc., patches `sys.argv`, calls `main()`, and verifies the correct function was dispatched.

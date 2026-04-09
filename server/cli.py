"""Unified server CLI for The Ages II."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _read_pid_file() -> dict | None:
    """Read multi-line PID file. Returns dict with pid, host, port, log_path or None."""
    pid_path = BASE_DIR / "data" / "server.pid"
    try:
        lines = pid_path.read_text().strip().splitlines()
        result: dict = {"pid": int(lines[0])}
        if len(lines) >= 2:
            result["host"] = lines[1]
        if len(lines) >= 3:
            result["port"] = int(lines[2])
        if len(lines) >= 4:
            result["log_path"] = lines[3]
        return result
    except (FileNotFoundError, IndexError, ValueError):
        return None


def _write_pid_file(pid: int, host: str, port: int, log_path: str) -> None:
    """Write multi-line PID file."""
    pid_path = BASE_DIR / "data" / "server.pid"
    pid_path.write_text(f"{pid}\n{host}\n{port}\n{log_path}\n")


def _remove_pid_file() -> None:
    """Remove PID file idempotently."""
    try:
        (BASE_DIR / "data" / "server.pid").unlink()
    except FileNotFoundError:
        pass


def _check_process_alive(pid: int) -> bool | None:
    """Check if process is alive. Returns True, False, or None (PermissionError)."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return None


def _verify_process_identity(pid: int) -> bool | None:
    """Verify process is uvicorn via ps. Returns True/False, or None if ps unavailable."""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            # ps found but process not in table — treat as not uvicorn
            return False
        return "uvicorn" in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("Warning: could not verify process identity (ps not available)")
        return None


def _check_running() -> dict | None:
    """Check if server is running. Returns PID info dict or None.

    Cleans up stale PID files automatically.
    """
    info = _read_pid_file()
    if info is None:
        return None

    pid = info["pid"]
    alive = _check_process_alive(pid)

    if alive is False:
        print(f"Warning: stale PID file found (PID {pid} is dead). Cleaning up.")
        _remove_pid_file()
        return None

    if alive is None:
        # PermissionError — process exists but owned by another user
        info["permission_error"] = True
        return info

    # Process is alive — verify identity
    identity = _verify_process_identity(pid)
    if identity is False:
        print(f"Warning: PID {pid} was recycled by another process. Cleaning up.")
        _remove_pid_file()
        return None

    # identity is None means ps unavailable — assume it's our server (safe default)
    return info


def cmd_start(args: argparse.Namespace) -> None:
    """Start the server."""
    if args.foreground and args.log_file:
        print("Error: --log-file cannot be used with --foreground")
        sys.exit(1)

    running = _check_running()
    if running:
        pid = running["pid"]
        if running.get("permission_error"):
            print(f"Error: server may be running as a different user (PID {pid})")
        else:
            print(f"Error: server is already running (PID {pid})")
        sys.exit(1)

    # Deferred import to avoid triggering Settings() on --help/--version
    from server.core.config import settings

    host = args.host if args.host is not None else settings.HOST
    port = args.port if args.port is not None else settings.PORT

    if args.foreground:
        import uvicorn
        print(f"Starting server in foreground on {host}:{port}")
        uvicorn.run("server.app:app", host=host, port=port)
        return

    # Daemon mode
    log_dir = BASE_DIR / "logs"
    os.makedirs(log_dir, exist_ok=True)

    if args.log_file:
        log_path = str(Path(args.log_file).resolve())
    else:
        log_path = str(log_dir / "server.log")

    cmd = [
        sys.executable, "-m", "uvicorn", "server.app:app",
        "--host", str(host),
        "--port", str(port),
    ]

    log_fd = open(log_path, "a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=str(BASE_DIR),
        )
    finally:
        log_fd.close()

    _write_pid_file(proc.pid, str(host), port, log_path)

    # Verify startup — poll every 0.5s for 3s
    for _ in range(6):
        time.sleep(0.5)
        alive = _check_process_alive(proc.pid)
        if alive is False:
            print("Error: server failed to start. Last 10 lines of log:")
            try:
                with open(log_path, encoding="utf-8") as f:
                    lines = f.readlines()
                for line in lines[-10:]:
                    print(f"  {line.rstrip()}")
            except FileNotFoundError:
                print("  (no log file found)")
            _remove_pid_file()
            sys.exit(1)

    print(f"Server started (PID {proc.pid})")
    print(f"  Logs: {log_path}")
    print(f"  Listening on {host}:{port}")
    print()
    print("  View logs:  ages-server logs --follow")
    print("  Stop:       ages-server stop")


def cmd_stop(args: argparse.Namespace) -> None:
    """Stop the server."""
    info = _read_pid_file()
    if info is None:
        print("Server is not running")
        sys.exit(0)

    pid = info["pid"]
    alive = _check_process_alive(pid)

    if alive is False:
        print(f"Server is not running (stale PID file cleaned up)")
        _remove_pid_file()
        sys.exit(0)

    if alive is None:
        print(f"Error: permission denied. Server may be running as a different user (PID {pid})")
        sys.exit(1)

    # Verify identity before sending signal
    identity = _verify_process_identity(pid)
    if identity is False:
        print(f"Warning: PID {pid} was recycled by another process. Cleaning up stale PID file.")
        _remove_pid_file()
        print("Server is not running")
        sys.exit(0)

    force = getattr(args, "force", False)
    timeout = 3 if force else 10

    if force:
        print("Warning: --force will kill the server without saving player state. Proceeding...")

    try:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            _remove_pid_file()
            print("Server stopped")
            return
        print(f"Stopping server (PID {pid})...")

        for _ in range(timeout * 2):
            time.sleep(0.5)
            if _check_process_alive(pid) is False:
                _remove_pid_file()
                print("Server stopped")
                return

        if force:
            print("Server did not stop gracefully. Sending SIGKILL...")
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            time.sleep(0.5)
            _remove_pid_file()
            print("Server killed")
        else:
            print(f"Error: server (PID {pid}) did not stop within {timeout}s. Use --force to kill.")
            sys.exit(1)
    except KeyboardInterrupt:
        _remove_pid_file()
        raise


def cmd_restart(args: argparse.Namespace) -> None:
    """Restart the server."""
    # Read current params from PID file before stopping
    info = _read_pid_file()
    preserved_host = info.get("host") if info else None
    preserved_port = info.get("port") if info else None

    if info is not None:
        try:
            cmd_stop(args)
        except SystemExit as e:
            if e.code != 0:
                raise
        time.sleep(1)

    # Build start args, preserving params from PID file if not overridden
    start_args = argparse.Namespace(
        host=args.host if args.host is not None else preserved_host,
        port=args.port if args.port is not None else preserved_port,
        log_file=getattr(args, "log_file", None),
        foreground=False,
    )
    cmd_start(start_args)


def cmd_status(args: argparse.Namespace) -> None:
    """Show server status."""
    info = _read_pid_file()
    if info is None:
        print("Server is not running")
        sys.exit(0)

    pid = info["pid"]
    alive = _check_process_alive(pid)

    if alive is False:
        print("Server is not running")
        _remove_pid_file()
        sys.exit(0)

    if alive is None:
        print(f"Server may be running as a different user (PID {pid})")
        sys.exit(0)

    # Verify identity
    identity = _verify_process_identity(pid)
    if identity is False:
        print("Server is not running")
        _remove_pid_file()
        sys.exit(0)

    host = info.get("host", "0.0.0.0")
    port = info.get("port", 8000)
    print(f"Server is running (PID {pid})")

    # Health check — 0.0.0.0 is not routable on macOS, use loopback instead
    check_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{check_host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = resp.read().decode()
        try:
            body = json.loads(data)
        except (json.JSONDecodeError, ValueError):
            print("  Health: unhealthy (malformed response)")
            print(f"  Listening on {host}:{port}")
            return
        if body.get("status") == "ok":
            print("  Health: healthy")
        else:
            print("  Health: unhealthy (unexpected response)")
    except (OSError, urllib.error.URLError):
        print("  Health: unreachable (server may be starting up or stuck)")

    print(f"  Listening on {host}:{port}")


def cmd_logs(args: argparse.Namespace) -> None:
    """Show server logs."""
    info = _read_pid_file()
    if info and "log_path" in info:
        log_path = info["log_path"]
    else:
        log_path = str(BASE_DIR / "logs" / "server.log")

    if not Path(log_path).exists():
        print(f"No log file found at {log_path}")
        sys.exit(1)

    lines = getattr(args, "lines", 50) or 50

    try:
        if getattr(args, "follow", False):
            os.execvp("tail", ["tail", "-f", "-n", str(lines), log_path])
        else:
            subprocess.run(["tail", "-n", str(lines), log_path], timeout=30)
    except subprocess.TimeoutExpired:
        print("Error: tail command timed out")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: 'tail' command not found")
        sys.exit(1)


def _get_version() -> str:
    """Get package version."""
    try:
        from importlib.metadata import PackageNotFoundError, version
        return version("the-ages-server")
    except PackageNotFoundError:
        return "unknown (run `pip install -e .`)"


def main() -> None:
    """Entry point for ages-server CLI."""
    if sys.platform == "win32":
        print("This command requires a POSIX system (Linux/macOS)")
        sys.exit(1)

    parser = argparse.ArgumentParser(
        prog="ages-server",
        description="The Ages II — Server Management CLI",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s {_get_version()}",
    )
    parser.set_defaults(func=None)

    subparsers = parser.add_subparsers(dest="command")

    # start
    start_parser = subparsers.add_parser("start", help="Start the server")
    start_parser.add_argument("--host", default=None, help="Host to bind to")
    start_parser.add_argument("--port", type=int, default=None, help="Port to bind to")
    start_parser.add_argument("--log-file", default=None, help="Custom log file path")
    start_parser.add_argument("--foreground", action="store_true", help="Run in foreground (no daemon)")
    start_parser.set_defaults(func=cmd_start)

    # stop
    stop_parser = subparsers.add_parser("stop", help="Stop the server")
    stop_parser.add_argument("--force", action="store_true", help="Force kill after 3s timeout")
    stop_parser.set_defaults(func=cmd_stop)

    # restart
    restart_parser = subparsers.add_parser("restart", help="Restart the server")
    restart_parser.add_argument("--force", action="store_true", help="Force kill during stop")
    restart_parser.add_argument("--host", default=None, help="Host to bind to")
    restart_parser.add_argument("--port", type=int, default=None, help="Port to bind to")
    restart_parser.add_argument("--log-file", default=None, help="Custom log file path")
    restart_parser.set_defaults(func=cmd_restart)

    # status
    status_parser = subparsers.add_parser("status", help="Show server status")
    status_parser.set_defaults(func=cmd_status)

    # logs
    logs_parser = subparsers.add_parser("logs", help="Show server logs")
    logs_parser.add_argument("--follow", "-f", action="store_true", help="Follow log output")
    logs_parser.add_argument("--lines", "-n", type=int, default=50, help="Number of lines to show")
    logs_parser.set_defaults(func=cmd_logs)

    args = parser.parse_args()
    if args.func is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()

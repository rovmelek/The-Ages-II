"""Tests for the unified server CLI (server/cli.py)."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch, call

import pytest

from server.cli import (
    BASE_DIR,
    _check_process_alive,
    _check_running,
    _get_version,
    _read_pid_file,
    _remove_pid_file,
    _verify_process_identity,
    _write_pid_file,
    cmd_logs,
    cmd_restart,
    cmd_start,
    cmd_status,
    cmd_stop,
    main,
)


PID_PATH = BASE_DIR / "data" / "server.pid"


# --- PID file helpers ---


class TestReadPidFile:
    """Tests for _read_pid_file."""

    def test_returns_none_when_no_file(self, tmp_path, monkeypatch):
        """Returns None when PID file does not exist."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        assert _read_pid_file() is None

    def test_reads_4_line_format(self, tmp_path, monkeypatch):
        """Reads standard 4-line PID file format."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")
        result = _read_pid_file()
        assert result == {"pid": 1234, "host": "0.0.0.0", "port": 8000, "log_path": "/tmp/log"}

    def test_handles_malformed_pid_file(self, tmp_path, monkeypatch):
        """Returns None for malformed PID file."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("not_a_number\n")
        assert _read_pid_file() is None

    def test_handles_empty_file(self, tmp_path, monkeypatch):
        """Returns None for empty PID file."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("")
        assert _read_pid_file() is None

    def test_handles_partial_pid_file(self, tmp_path, monkeypatch):
        """Reads partial PID file gracefully (only PID line)."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n")
        result = _read_pid_file()
        assert result == {"pid": 1234}


class TestWritePidFile:
    """Tests for _write_pid_file."""

    def test_writes_4_line_format(self, tmp_path, monkeypatch):
        """Writes PID file in correct 4-line format."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        _write_pid_file(1234, "0.0.0.0", 8000, "/tmp/log")
        content = (tmp_path / "data" / "server.pid").read_text()
        assert content == "1234\n0.0.0.0\n8000\n/tmp/log\n"


class TestRemovePidFile:
    """Tests for _remove_pid_file."""

    def test_removes_existing_file(self, tmp_path, monkeypatch):
        """Removes PID file when it exists."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        pid_file = tmp_path / "data" / "server.pid"
        pid_file.write_text("1234\n")
        _remove_pid_file()
        assert not pid_file.exists()

    def test_no_error_when_missing(self, tmp_path, monkeypatch):
        """No error when PID file does not exist."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        _remove_pid_file()  # Should not raise


# --- Process checks ---


class TestCheckProcessAlive:
    """Tests for _check_process_alive."""

    def test_returns_true_for_alive_process(self):
        """Returns True for a running process."""
        with patch("server.cli.os.kill") as mock_kill:
            mock_kill.return_value = None
            assert _check_process_alive(1234) is True

    def test_returns_false_for_dead_process(self):
        """Returns False when process does not exist."""
        with patch("server.cli.os.kill", side_effect=ProcessLookupError):
            assert _check_process_alive(1234) is False

    def test_returns_none_for_permission_error(self):
        """Returns None when process exists but belongs to another user."""
        with patch("server.cli.os.kill", side_effect=PermissionError):
            assert _check_process_alive(1234) is None


class TestVerifyProcessIdentity:
    """Tests for _verify_process_identity."""

    def test_returns_true_for_uvicorn(self):
        """Returns True when ps shows uvicorn in command."""
        with patch("server.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="python -m uvicorn server.app:app")
            assert _verify_process_identity(1234) is True

    def test_returns_false_for_non_uvicorn(self):
        """Returns False when ps shows a different process."""
        with patch("server.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="/usr/bin/bash")
            assert _verify_process_identity(1234) is False

    def test_returns_none_when_ps_not_found(self, capsys):
        """Returns None and prints warning when ps is not available."""
        with patch("server.cli.subprocess.run", side_effect=FileNotFoundError):
            result = _verify_process_identity(1234)
        assert result is None
        assert "could not verify process identity" in capsys.readouterr().out

    def test_returns_false_when_ps_finds_no_process(self):
        """Returns False when ps returns non-zero (process not in table)."""
        with patch("server.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = _verify_process_identity(1234)
        assert result is False


class TestCheckRunning:
    """Tests for _check_running."""

    def test_returns_none_when_no_pid_file(self, tmp_path, monkeypatch):
        """Returns None when no PID file exists."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        assert _check_running() is None

    def test_cleans_stale_pid(self, tmp_path, monkeypatch):
        """Cleans up stale PID file when process is dead."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("99999\n0.0.0.0\n8000\n/tmp/log\n")
        with patch("server.cli._check_process_alive", return_value=False):
            assert _check_running() is None
        assert not (tmp_path / "data" / "server.pid").exists()

    def test_cleans_recycled_pid(self, tmp_path, monkeypatch):
        """Cleans up PID file when process is alive but not uvicorn."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")
        with patch("server.cli._check_process_alive", return_value=True), \
             patch("server.cli._verify_process_identity", return_value=False):
            assert _check_running() is None
        assert not (tmp_path / "data" / "server.pid").exists()

    def test_returns_info_when_running(self, tmp_path, monkeypatch):
        """Returns PID info when server is running and identity verified."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")
        with patch("server.cli._check_process_alive", return_value=True), \
             patch("server.cli._verify_process_identity", return_value=True):
            result = _check_running()
        assert result["pid"] == 1234

    def test_returns_info_with_permission_error(self, tmp_path, monkeypatch):
        """Returns info with permission_error flag for different-user process."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")
        with patch("server.cli._check_process_alive", return_value=None):
            result = _check_running()
        assert result["permission_error"] is True


# --- cmd_start ---


class TestCmdStart:
    """Tests for cmd_start."""

    def test_refuses_when_already_running(self, tmp_path, monkeypatch):
        """Exits with error when server is already running."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        with patch("server.cli._check_running", return_value={"pid": 1234}):
            with pytest.raises(SystemExit, match="1"):
                cmd_start(argparse.Namespace(host=None, port=None, log_file=None, foreground=False))

    def test_foreground_and_log_file_mutual_exclusion(self):
        """Exits with error when --foreground and --log-file are both set."""
        with pytest.raises(SystemExit, match="1"):
            cmd_start(argparse.Namespace(host=None, port=None, log_file="/tmp/log", foreground=True))

    def test_foreground_runs_uvicorn_directly(self, monkeypatch):
        """Foreground mode calls uvicorn.run directly, no Popen."""
        mock_settings = MagicMock(HOST="0.0.0.0", PORT=8000)
        monkeypatch.setattr("server.cli._check_running", lambda: None)

        with patch.dict("sys.modules", {"server.core.config": MagicMock(settings=mock_settings)}), \
             patch("uvicorn.run") as mock_uvicorn:
            cmd_start(argparse.Namespace(host=None, port=None, log_file=None, foreground=True))
            mock_uvicorn.assert_called_once_with("server.app:app", host="0.0.0.0", port=8000)

    def test_daemon_start_writes_pid_file(self, tmp_path, monkeypatch):
        """Daemon mode writes PID file and verifies startup."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "logs").mkdir()

        mock_settings = MagicMock(HOST="0.0.0.0", PORT=8000)
        mock_proc = MagicMock(pid=5678)
        log_file = tmp_path / "logs" / "server.log"
        log_file.touch()

        original_open = open

        def patched_open(path, *a, **kw):
            # Let PID file writes go through to real filesystem
            path_str = str(path)
            if "server.pid" in path_str or str(tmp_path) in path_str:
                return original_open(path, *a, **kw)
            return mock_open()()

        with patch("server.cli._check_running", return_value=None), \
             patch.dict("sys.modules", {"server.core.config": MagicMock(settings=mock_settings)}), \
             patch("server.cli.subprocess.Popen", return_value=mock_proc), \
             patch("server.cli._check_process_alive", return_value=True), \
             patch("server.cli.time.sleep"), \
             patch("builtins.open", side_effect=patched_open):
            cmd_start(argparse.Namespace(host=None, port=None, log_file=None, foreground=False))

        pid_content = (tmp_path / "data" / "server.pid").read_text()
        assert "5678" in pid_content

    def test_startup_failure_shows_log_tail(self, tmp_path, monkeypatch, capsys):
        """Shows last 10 log lines when server fails to start."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "logs").mkdir()
        log_path = tmp_path / "logs" / "server.log"
        log_path.write_text("line1\nline2\nerror: port in use\n")

        mock_settings = MagicMock(HOST="0.0.0.0", PORT=8000)
        mock_proc = MagicMock(pid=5678)

        original_open = open

        def patched_open(path, *a, **kw):
            path_str = str(path)
            if str(tmp_path) in path_str:
                return original_open(path, *a, **kw)
            return mock_open()()

        with patch("server.cli._check_running", return_value=None), \
             patch.dict("sys.modules", {"server.core.config": MagicMock(settings=mock_settings)}), \
             patch("server.cli.subprocess.Popen", return_value=mock_proc), \
             patch("server.cli._check_process_alive", return_value=False), \
             patch("server.cli.time.sleep"), \
             patch("builtins.open", side_effect=patched_open):
            with pytest.raises(SystemExit, match="1"):
                cmd_start(argparse.Namespace(host=None, port=None, log_file=None, foreground=False))

        output = capsys.readouterr().out
        assert "failed to start" in output
        assert "port in use" in output

    def test_host_port_override(self, tmp_path, monkeypatch):
        """--host and --port flags override Settings defaults."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "logs").mkdir()

        mock_settings = MagicMock(HOST="0.0.0.0", PORT=8000)
        mock_proc = MagicMock(pid=5678)

        with patch("server.cli._check_running", return_value=None), \
             patch.dict("sys.modules", {"server.core.config": MagicMock(settings=mock_settings)}), \
             patch("server.cli.subprocess.Popen", return_value=mock_proc) as mock_popen, \
             patch("server.cli._check_process_alive", return_value=True), \
             patch("server.cli.time.sleep"), \
             patch("builtins.open", mock_open()):
            cmd_start(argparse.Namespace(host="127.0.0.1", port=9000, log_file=None, foreground=False))

        popen_cmd = mock_popen.call_args[0][0]
        assert "127.0.0.1" in popen_cmd
        assert "9000" in popen_cmd

    def test_custom_log_file_resolved(self, tmp_path, monkeypatch):
        """--log-file is resolved to absolute path."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()

        mock_settings = MagicMock(HOST="0.0.0.0", PORT=8000)
        mock_proc = MagicMock(pid=5678)

        with patch("server.cli._check_running", return_value=None), \
             patch.dict("sys.modules", {"server.core.config": MagicMock(settings=mock_settings)}), \
             patch("server.cli.subprocess.Popen", return_value=mock_proc), \
             patch("server.cli._check_process_alive", return_value=True), \
             patch("server.cli.time.sleep"), \
             patch("builtins.open", mock_open()):
            cmd_start(argparse.Namespace(host=None, port=None, log_file="custom.log", foreground=False))

        pid_content = (tmp_path / "data" / "server.pid").read_text()
        # log_path should be an absolute path
        log_line = pid_content.strip().splitlines()[3]
        assert os.path.isabs(log_line)


# --- cmd_stop ---


class TestCmdStop:
    """Tests for cmd_stop."""

    def test_no_pid_file_exits_clean(self, tmp_path, monkeypatch):
        """Exits cleanly with exit 0 when no PID file exists."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        with pytest.raises(SystemExit) as exc_info:
            cmd_stop(argparse.Namespace(force=False))
        assert exc_info.value.code == 0

    def test_stale_pid_cleaned_up(self, tmp_path, monkeypatch):
        """Cleans up stale PID file when process is dead."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("99999\n0.0.0.0\n8000\n/tmp/log\n")
        with patch("server.cli._check_process_alive", return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                cmd_stop(argparse.Namespace(force=False))
        assert exc_info.value.code == 0
        assert not (tmp_path / "data" / "server.pid").exists()

    def test_sends_sigterm(self, tmp_path, monkeypatch):
        """Sends SIGTERM to the server process."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")

        # First call: liveness check in cmd_stop, then poll loop: alive, alive, dead
        with patch("server.cli._check_process_alive", side_effect=[True, True, True, False]), \
             patch("server.cli._verify_process_identity", return_value=True), \
             patch("server.cli.os.kill") as mock_kill, \
             patch("server.cli.time.sleep"):
            cmd_stop(argparse.Namespace(force=False))

        mock_kill.assert_any_call(1234, signal.SIGTERM)

    def test_force_sends_sigkill_after_timeout(self, tmp_path, monkeypatch, capsys):
        """--force sends SIGKILL when SIGTERM doesn't work within 3s."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")

        # 1 initial liveness check + 6 loop polls (3s * 2), all alive → falls through to SIGKILL
        with patch("server.cli._check_process_alive", side_effect=[True] + [True] * 6), \
             patch("server.cli._verify_process_identity", return_value=True), \
             patch("server.cli.os.kill") as mock_kill, \
             patch("server.cli.time.sleep"):
            cmd_stop(argparse.Namespace(force=True))

        output = capsys.readouterr().out
        assert "Warning" in output
        mock_kill.assert_any_call(1234, signal.SIGKILL)

    def test_permission_error_handled(self, tmp_path, monkeypatch):
        """Exits with error when server is owned by another user."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")

        with patch("server.cli._check_process_alive", return_value=None):
            with pytest.raises(SystemExit, match="1"):
                cmd_stop(argparse.Namespace(force=False))

    def test_recycled_pid_cleaned(self, tmp_path, monkeypatch, capsys):
        """Cleans up PID file when PID was recycled by another process."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")

        with patch("server.cli._check_process_alive", return_value=True), \
             patch("server.cli._verify_process_identity", return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                cmd_stop(argparse.Namespace(force=False))
        assert exc_info.value.code == 0
        assert "recycled" in capsys.readouterr().out

    def test_interrupt_cleans_pid(self, tmp_path, monkeypatch):
        """PID file is cleaned up when stop is interrupted by Ctrl+C."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")

        with patch("server.cli._check_process_alive", return_value=True), \
             patch("server.cli._verify_process_identity", return_value=True), \
             patch("server.cli.os.kill") as mock_kill, \
             patch("server.cli.time.sleep", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                cmd_stop(argparse.Namespace(force=False))

        assert not (tmp_path / "data" / "server.pid").exists()

    def test_sigterm_race_process_dies_before_signal(self, tmp_path, monkeypatch, capsys):
        """Handles process dying between identity check and SIGTERM gracefully."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")

        with patch("server.cli._check_process_alive", return_value=True), \
             patch("server.cli._verify_process_identity", return_value=True), \
             patch("server.cli.os.kill", side_effect=ProcessLookupError):
            cmd_stop(argparse.Namespace(force=False))

        assert not (tmp_path / "data" / "server.pid").exists()
        assert "stopped" in capsys.readouterr().out.lower()

    def test_failed_stop_preserves_pid_file(self, tmp_path, monkeypatch):
        """PID file is preserved when stop fails (server didn't stop)."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")

        # Process stays alive through all 20 polls
        with patch("server.cli._check_process_alive", return_value=True), \
             patch("server.cli._verify_process_identity", return_value=True), \
             patch("server.cli.os.kill"), \
             patch("server.cli.time.sleep"):
            with pytest.raises(SystemExit, match="1"):
                cmd_stop(argparse.Namespace(force=False))

        assert (tmp_path / "data" / "server.pid").exists()


# --- cmd_restart ---


class TestCmdRestart:
    """Tests for cmd_restart."""

    def test_preserves_host_port_from_pid_file(self, tmp_path, monkeypatch):
        """Restart preserves host/port from PID file when not overridden."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n127.0.0.1\n9000\n/tmp/log\n")

        with patch("server.cli.cmd_stop") as mock_stop, \
             patch("server.cli.cmd_start") as mock_start, \
             patch("server.cli.time.sleep"):
            cmd_restart(argparse.Namespace(host=None, port=None, log_file=None, force=False))

        start_args = mock_start.call_args[0][0]
        assert start_args.host == "127.0.0.1"
        assert start_args.port == 9000

    def test_passes_force_to_stop(self, tmp_path, monkeypatch):
        """--force flag is passed through to stop."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")

        with patch("server.cli.cmd_stop") as mock_stop, \
             patch("server.cli.cmd_start"), \
             patch("server.cli.time.sleep"):
            args = argparse.Namespace(host=None, port=None, log_file=None, force=True)
            cmd_restart(args)

        stop_args = mock_stop.call_args[0][0]
        assert stop_args.force is True

    def test_proceeds_when_not_running(self, tmp_path, monkeypatch):
        """Starts server when it's not currently running."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()

        with patch("server.cli.cmd_start") as mock_start:
            cmd_restart(argparse.Namespace(host=None, port=None, log_file=None, force=False))

        mock_start.assert_called_once()

    def test_aborts_if_stop_fails(self, tmp_path, monkeypatch):
        """Does not start if stop fails with non-zero exit."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")

        with patch("server.cli.cmd_stop", side_effect=SystemExit(1)), \
             patch("server.cli.cmd_start") as mock_start:
            with pytest.raises(SystemExit, match="1"):
                cmd_restart(argparse.Namespace(host=None, port=None, log_file=None, force=False))

        mock_start.assert_not_called()


# --- cmd_status ---


class TestCmdStatus:
    """Tests for cmd_status."""

    def test_not_running(self, tmp_path, monkeypatch):
        """Reports server not running when no PID file."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        with pytest.raises(SystemExit) as exc_info:
            cmd_status(argparse.Namespace())
        assert exc_info.value.code == 0

    def test_healthy_status(self, tmp_path, monkeypatch, capsys):
        """Reports healthy when server responds with {"status": "ok"}."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"status": "ok"}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("server.cli._check_process_alive", return_value=True), \
             patch("server.cli._verify_process_identity", return_value=True), \
             patch("server.cli.urllib.request.urlopen", return_value=mock_resp):
            cmd_status(argparse.Namespace())

        output = capsys.readouterr().out
        assert "healthy" in output
        assert "PID 1234" in output

    def test_unhealthy_status(self, tmp_path, monkeypatch, capsys):
        """Reports unhealthy for unexpected health response body."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"status": "weird"}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("server.cli._check_process_alive", return_value=True), \
             patch("server.cli._verify_process_identity", return_value=True), \
             patch("server.cli.urllib.request.urlopen", return_value=mock_resp):
            cmd_status(argparse.Namespace())

        output = capsys.readouterr().out
        assert "unhealthy" in output

    def test_unreachable_status(self, tmp_path, monkeypatch, capsys):
        """Reports unreachable when health endpoint fails."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")

        with patch("server.cli._check_process_alive", return_value=True), \
             patch("server.cli._verify_process_identity", return_value=True), \
             patch("server.cli.urllib.request.urlopen", side_effect=ConnectionRefusedError):
            cmd_status(argparse.Namespace())

        output = capsys.readouterr().out
        assert "unreachable" in output

    def test_permission_error_status(self, tmp_path, monkeypatch, capsys):
        """Reports permission issue for different-user process."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "server.pid").write_text("1234\n0.0.0.0\n8000\n/tmp/log\n")

        with patch("server.cli._check_process_alive", return_value=None):
            with pytest.raises(SystemExit) as exc_info:
                cmd_status(argparse.Namespace())
        assert exc_info.value.code == 0
        assert "different user" in capsys.readouterr().out


# --- cmd_logs ---


class TestCmdLogs:
    """Tests for cmd_logs."""

    def test_reads_log_path_from_pid_file(self, tmp_path, monkeypatch):
        """Uses log path from PID file when available."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        log_path = str(tmp_path / "custom.log")
        (tmp_path / "data" / "server.pid").write_text(f"1234\n0.0.0.0\n8000\n{log_path}\n")
        Path(log_path).write_text("log content\n")

        with patch("server.cli.subprocess.run") as mock_run:
            cmd_logs(argparse.Namespace(follow=False, lines=50))

        mock_run.assert_called_once_with(["tail", "-n", "50", log_path], timeout=30)

    def test_falls_back_to_default_when_no_pid(self, tmp_path, monkeypatch):
        """Falls back to default log path when no PID file."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        default_log = tmp_path / "logs" / "server.log"
        default_log.parent.mkdir()
        default_log.write_text("log content\n")

        with patch("server.cli.subprocess.run") as mock_run:
            cmd_logs(argparse.Namespace(follow=False, lines=50))

        mock_run.assert_called_once_with(["tail", "-n", "50", str(default_log)], timeout=30)

    def test_follow_uses_execvp(self, tmp_path, monkeypatch):
        """--follow uses os.execvp with tail -f."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        log_path = tmp_path / "logs" / "server.log"
        log_path.parent.mkdir()
        log_path.write_text("log content\n")

        with patch("server.cli.os.execvp") as mock_exec:
            cmd_logs(argparse.Namespace(follow=True, lines=50))

        mock_exec.assert_called_once_with("tail", ["tail", "-f", "-n", "50", str(log_path)])

    def test_missing_log_file_exits(self, tmp_path, monkeypatch):
        """Exits with error when log file does not exist."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()

        with pytest.raises(SystemExit, match="1"):
            cmd_logs(argparse.Namespace(follow=False, lines=50))

    def test_tail_not_found(self, tmp_path, monkeypatch, capsys):
        """Exits with error when tail command is not available."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        log_path = tmp_path / "logs" / "server.log"
        log_path.parent.mkdir()
        log_path.write_text("log content\n")

        with patch("server.cli.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(SystemExit, match="1"):
                cmd_logs(argparse.Namespace(follow=False, lines=50))
        assert "tail" in capsys.readouterr().out

    def test_tail_timeout(self, tmp_path, monkeypatch, capsys):
        """Exits with error when tail command times out."""
        monkeypatch.setattr("server.cli.BASE_DIR", tmp_path)
        (tmp_path / "data").mkdir()
        log_path = tmp_path / "logs" / "server.log"
        log_path.parent.mkdir()
        log_path.write_text("log content\n")

        with patch("server.cli.subprocess.run", side_effect=subprocess.TimeoutExpired("tail", 30)):
            with pytest.raises(SystemExit, match="1"):
                cmd_logs(argparse.Namespace(follow=False, lines=50))
        assert "timed out" in capsys.readouterr().out


# --- Version ---


class TestVersion:
    """Tests for _get_version."""

    def test_returns_version_when_installed(self):
        """Returns package version when installed."""
        with patch("importlib.metadata.version", return_value="0.1.0"):
            result = _get_version()
        assert result == "0.1.0"

    def test_returns_unknown_when_not_installed(self):
        """Returns unknown string when package is not installed."""
        from importlib.metadata import PackageNotFoundError
        with patch("importlib.metadata.version", side_effect=PackageNotFoundError):
            result = _get_version()
        assert "unknown" in result


# --- main() dispatch ---


class TestMain:
    """Tests for main() entry point."""

    def test_dispatches_start(self, monkeypatch):
        """main() dispatches to cmd_start for 'start' subcommand."""
        monkeypatch.setattr("sys.argv", ["ages-server", "start", "--foreground"])
        with patch("server.cli.cmd_start") as mock_cmd:
            main()
        mock_cmd.assert_called_once()

    def test_dispatches_stop(self, monkeypatch):
        """main() dispatches to cmd_stop for 'stop' subcommand."""
        monkeypatch.setattr("sys.argv", ["ages-server", "stop"])
        with patch("server.cli.cmd_stop") as mock_cmd:
            main()
        mock_cmd.assert_called_once()

    def test_dispatches_status(self, monkeypatch):
        """main() dispatches to cmd_status for 'status' subcommand."""
        monkeypatch.setattr("sys.argv", ["ages-server", "status"])
        with patch("server.cli.cmd_status") as mock_cmd:
            main()
        mock_cmd.assert_called_once()

    def test_dispatches_restart(self, monkeypatch):
        """main() dispatches to cmd_restart for 'restart' subcommand."""
        monkeypatch.setattr("sys.argv", ["ages-server", "restart"])
        with patch("server.cli.cmd_restart") as mock_cmd:
            main()
        mock_cmd.assert_called_once()

    def test_dispatches_logs(self, monkeypatch):
        """main() dispatches to cmd_logs for 'logs' subcommand."""
        monkeypatch.setattr("sys.argv", ["ages-server", "logs"])
        with patch("server.cli.cmd_logs") as mock_cmd:
            main()
        mock_cmd.assert_called_once()

    def test_no_subcommand_prints_help(self, monkeypatch, capsys):
        """No subcommand prints help and exits 0."""
        monkeypatch.setattr("sys.argv", ["ages-server"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_windows_guard(self, monkeypatch):
        """Exits with error on Windows."""
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("sys.argv", ["ages-server", "start"])
        with pytest.raises(SystemExit, match="1"):
            main()

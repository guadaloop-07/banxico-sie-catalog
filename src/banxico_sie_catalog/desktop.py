"""Persistent desktop helpers for secure Codex installations."""

from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from .installer import DEFAULT_REPOSITORY, install_catalog_release
from .secrets import SecureTokenError, get_token, require_keyring, set_token


class DesktopSetupError(Exception):
    """Raised when persistent desktop operations cannot complete."""


def default_install_dir() -> Path:
    root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "banxico-sie-catalog"


def update_now(
    install_dir: Path, release: str, repository: str = DEFAULT_REPOSITORY
) -> dict[str, object]:
    """Install a verified release beside the old snapshot, then atomically activate it."""
    snapshot = install_dir / "snapshot"
    staging = install_dir / ".snapshot-next"
    backup = install_dir / ".snapshot-previous"
    if staging.exists():
        shutil.rmtree(staging)
    result = install_catalog_release(repository, release, staging)
    if backup.exists():
        shutil.rmtree(backup)
    try:
        if snapshot.exists():
            snapshot.replace(backup)
        staging.replace(snapshot)
    except OSError as error:
        if backup.exists() and not snapshot.exists():
            backup.replace(snapshot)
        raise DesktopSetupError(f"Could not activate the updated catalog: {error}") from error
    shutil.rmtree(backup, ignore_errors=True)
    state = {
        "release": result["release"],
        "repository": repository,
        "last_update": datetime.now(UTC).isoformat(),
    }
    install_dir.mkdir(parents=True, exist_ok=True)
    (install_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    result["destination"] = str(snapshot)
    return result


def schedule_monthly_updates(
    install_dir: Path, release: str, repository: str = DEFAULT_REPOSITORY
) -> None:
    """Install a per-user Linux systemd timer; it is not a permanent process."""
    if sys.platform != "linux" or shutil.which("systemctl") is None:
        raise DesktopSetupError("Automatic updates require Linux with systemd --user.")
    unit_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    command = (
        f"{sys.executable} -m banxico_sie_catalog.cli update-now "
        f"--install-dir {install_dir} --release {release} --repository {repository}"
    )
    (unit_dir / "banxico-sie-catalog-update.service").write_text(
        (
            "[Unit]\nDescription=Refresh Banxico SIE catalog\n\n"
            f"[Service]\nType=oneshot\nExecStart={command}\n"
        ),
        encoding="utf-8",
    )
    (unit_dir / "banxico-sie-catalog-update.timer").write_text(
        (
            "[Timer]\nOnCalendar=monthly\nRandomizedDelaySec=8h\nPersistent=true\n\n"
            "[Install]\nWantedBy=timers.target\n"
        ),
        encoding="utf-8",
    )
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, capture_output=True)
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", "banxico-sie-catalog-update.timer"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as error:
        raise DesktopSetupError("Could not enable the monthly update timer.") from error


def doctor(install_dir: Path) -> dict[str, object]:
    """Return status without returning or logging a token."""
    try:
        keyring_available = True
        token_available = bool(get_token())
    except SecureTokenError:
        keyring_available = token_available = False
    state_path = install_dir / "state.json"
    return {
        "keyring_available": keyring_available,
        "token_available": token_available,
        "catalog_available": (install_dir / "snapshot" / "catalog.sqlite").is_file(),
        "state": json.loads(state_path.read_text()) if state_path.exists() else {},
    }


def setup_codex(
    install_dir: Path, release: str, schedule: bool, repository: str = DEFAULT_REPOSITORY
) -> dict[str, object]:
    """Run the single-installation desktop flow for a standard graphical user."""
    require_keyring()
    token = getpass.getpass("Banxico token: ")
    from .api import SIEAPIClient

    SIEAPIClient(token=token).validate(["SF1"])
    set_token(token)
    try:
        result = update_now(install_dir, release, repository)
        codex = shutil.which("codex")
        if codex is None:
            raise DesktopSetupError("Codex CLI was not found on PATH.")
        subprocess.run(
            [codex, "mcp", "remove", "banxico_sie_catalog"],
            check=False,
            capture_output=True,
        )
        command = [codex, "mcp", "add", "banxico_sie_catalog"]
        for variable in ("DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR"):
            if value := os.environ.get(variable):
                command.extend(["--env", f"{variable}={value}"])
        command.extend(
            [
                "--",
                sys.executable,
                "-m",
                "banxico_sie_catalog.mcp_server",
                "--database",
                str((install_dir / "snapshot" / "catalog.sqlite").resolve()),
            ]
        )
        subprocess.run(command, check=True, capture_output=True)
        if schedule:
            schedule_monthly_updates(install_dir, release, repository)
        return result
    except Exception:
        # A failed repair must not remove a working user secret.
        raise

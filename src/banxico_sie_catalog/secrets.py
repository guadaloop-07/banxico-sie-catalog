"""Secure storage for the Banxico API token."""

from __future__ import annotations

import os

SERVICE_NAME = "banxico-sie-catalog"
ACCOUNT_NAME = "bmx-token"


class SecureTokenError(Exception):
    """Raised when the system keyring cannot safely store a token."""


def _keyring():
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError as error:
        raise SecureTokenError("Secure token storage is not installed.") from error
    return keyring, KeyringError


def require_keyring() -> None:
    """Fail closed when a desktop keyring backend is unavailable."""
    keyring, _ = _keyring()
    if getattr(keyring.get_keyring(), "priority", 0) <= 0:
        raise SecureTokenError("No desktop keyring is available. Unlock it before setup.")


def get_token() -> str | None:
    """Read an explicit environment token or the persisted desktop secret."""
    if token := os.environ.get("BMX_TOKEN"):
        return token
    keyring, keyring_error = _keyring()
    try:
        return keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
    except keyring_error as error:
        raise SecureTokenError("Could not read the token from the system keyring.") from error


def set_token(token: str) -> None:
    """Save a non-empty token in the system keyring."""
    if not token.strip():
        raise SecureTokenError("The Banxico token cannot be empty.")
    require_keyring()
    keyring, keyring_error = _keyring()
    try:
        keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, token)
    except keyring_error as error:
        raise SecureTokenError("Could not save the token in the system keyring.") from error


def delete_token() -> bool:
    """Delete the persisted token without ever returning it."""
    keyring, keyring_error = _keyring()
    try:
        if keyring.get_password(SERVICE_NAME, ACCOUNT_NAME) is None:
            return False
        keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
    except keyring_error as error:
        raise SecureTokenError("Could not remove the token from the system keyring.") from error
    return True

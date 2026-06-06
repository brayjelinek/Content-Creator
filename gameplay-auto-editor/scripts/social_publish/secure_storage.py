"""Store OAuth tokens in the OS credential manager (never in config or logs)."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

SERVICE_NAME = "GameplayAutoEditor"


def save_token_bundle(platform: str, bundle: dict[str, Any]) -> None:
    """Persist token bundle to the OS keychain/credential manager."""
    import keyring

    keyring.set_password(SERVICE_NAME, _account_name(platform), json.dumps(bundle))
    logger.info("[SocialAuth] Stored credentials for %s in OS secure storage", platform)


def load_token_bundle(platform: str) -> dict[str, Any] | None:
    """Load token bundle from secure storage."""
    import keyring

    raw = keyring.get_password(SERVICE_NAME, _account_name(platform))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[SocialAuth] Invalid stored credential format for %s — clearing", platform)
        delete_token_bundle(platform)
        return None


def delete_token_bundle(platform: str) -> None:
    """Remove stored credentials for a platform."""
    import keyring

    try:
        keyring.delete_password(SERVICE_NAME, _account_name(platform))
        logger.info("[SocialAuth] Disconnected %s and cleared secure storage", platform)
    except keyring.errors.PasswordDeleteError:
        return


def storage_available() -> bool:
    """Return True when OS-backed secure storage is usable."""
    try:
        import keyring

        backend = keyring.get_keyring()
        return backend.__class__.__name__ not in {"FailKeyring", "NoKeyringAvailable"}
    except Exception:  # noqa: BLE001
        return False


def _account_name(platform: str) -> str:
    return f"social_oauth::{platform}"

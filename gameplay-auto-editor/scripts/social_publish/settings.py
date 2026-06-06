"""Load social publishing credentials from environment (never commit secrets)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class PlatformCredentials:
    client_id: str
    client_secret: str | None = None


@dataclass
class SocialPublishSettings:
    enabled: bool
    require_confirm: bool
    max_posts_per_session: int
    default_privacy: str
    youtube: PlatformCredentials
    tiktok: PlatformCredentials
    instagram: PlatformCredentials


def load_social_settings(config: dict | None = None) -> SocialPublishSettings:
    cfg = dict(config or {})
    social = dict(cfg.get("social_publish") or {})
    return SocialPublishSettings(
        enabled=bool(social.get("enabled", False)),
        require_confirm=bool(social.get("require_confirm", True)),
        max_posts_per_session=max(1, int(social.get("max_posts_per_session", 10))),
        default_privacy=str(social.get("default_privacy", "private")),
        youtube=_platform_credentials(
            "YOUTUBE_CLIENT_ID",
            "YOUTUBE_CLIENT_SECRET",
            social.get("youtube", {}),
        ),
        tiktok=_platform_credentials(
            "TIKTOK_CLIENT_KEY",
            "TIKTOK_CLIENT_SECRET",
            social.get("tiktok", {}),
        ),
        instagram=_platform_credentials(
            "META_APP_ID",
            "META_APP_SECRET",
            social.get("instagram", {}),
        ),
    )


def _platform_credentials(id_env: str, secret_env: str, block: dict) -> PlatformCredentials:
    client_id = str(block.get("client_id") or os.getenv(id_env) or "").strip()
    client_secret = str(block.get("client_secret") or os.getenv(secret_env) or "").strip() or None
    return PlatformCredentials(client_id=client_id, client_secret=client_secret)

"""Unified social publishing with security guardrails."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.social_publish import instagram, tiktok, youtube
from scripts.social_publish.secure_storage import storage_available
from scripts.social_publish.settings import SocialPublishSettings, load_social_settings
from scripts.social_publish.youtube import ConnectionStatus, PublishResult

logger = logging.getLogger(__name__)

AUDIT_FILENAME = "publish_audit.jsonl"
SUPPORTED_PLATFORMS = ("youtube", "tiktok", "instagram")


class SocialPublishManager:
    """Connect accounts and publish clips with confirmation, limits, and audit trail."""

    def __init__(self, config: dict[str, Any] | None = None, project_root: Path | None = None):
        self.config = dict(config or {})
        self.settings: SocialPublishSettings = load_social_settings(self.config)
        self.project_root = project_root or Path(__file__).resolve().parents[2]
        self._posts_this_session = 0
        self.audit_path = self.project_root / "logs" / AUDIT_FILENAME

    def is_enabled(self) -> bool:
        rollout = dict(self.config.get("rollout") or {})
        optional = dict(rollout.get("optional_features") or {})
        return bool(self.settings.enabled) and bool(optional.get("direct_publish", False))

    def storage_ready(self) -> bool:
        return storage_available()

    def platform_status(self) -> dict[str, ConnectionStatus]:
        return {
            "youtube": youtube.get_status(self.settings.youtube),
            "tiktok": tiktok.get_status(self.settings.tiktok),
            "instagram": instagram.get_status(self.settings.instagram),
        }

    def connect(self, platform: str) -> ConnectionStatus:
        platform = platform.lower()
        if not self.storage_ready():
            raise RuntimeError(
                "Secure token storage is unavailable on this system. "
                "Install a supported OS keychain backend before connecting accounts."
            )
        if platform == "youtube":
            return youtube.connect(self.settings.youtube)
        if platform == "tiktok":
            return tiktok.connect(self.settings.tiktok)
        if platform == "instagram":
            return instagram.connect(self.settings.instagram)
        raise ValueError(f"Unsupported platform: {platform}")

    def disconnect(self, platform: str) -> None:
        platform = platform.lower()
        if platform == "youtube":
            youtube.disconnect()
        elif platform == "tiktok":
            tiktok.disconnect()
        elif platform == "instagram":
            instagram.disconnect()
        else:
            raise ValueError(f"Unsupported platform: {platform}")

    def publish_clip(
        self,
        platform: str,
        video_path: Path,
        *,
        title: str = "",
        description: str = "",
        privacy: str | None = None,
        user_confirmed: bool = False,
    ) -> PublishResult:
        platform = platform.lower()
        video_path = Path(video_path)

        if not self.is_enabled():
            return PublishResult(
                False,
                platform,
                "Direct publishing is disabled. Enable social_publish.enabled and rollout.optional_features.direct_publish.",
            )

        if self.settings.require_confirm and not user_confirmed:
            return PublishResult(False, platform, "User confirmation is required before posting.")

        if self._posts_this_session >= self.settings.max_posts_per_session:
            return PublishResult(
                False,
                platform,
                f"Session post limit reached ({self.settings.max_posts_per_session}). Restart the app to post more.",
            )

        privacy_status = privacy or self._default_privacy(platform)
        title = (title or video_path.stem)[:100]
        description = description[:5000]

        try:
            if platform == "youtube":
                result = youtube.publish_clip(
                    self.settings.youtube,
                    video_path=video_path,
                    title=title,
                    description=description,
                    privacy_status=privacy_status,
                )
            elif platform == "tiktok":
                result = tiktok.publish_clip(
                    self.settings.tiktok,
                    video_path=video_path,
                    title=title,
                    description=description,
                    privacy_status=privacy_status,
                )
            elif platform == "instagram":
                result = instagram.publish_clip(
                    self.settings.instagram,
                    video_path=video_path,
                    title=title,
                    description=description,
                    privacy_status=privacy_status,
                )
            else:
                return PublishResult(False, platform, f"Unsupported platform: {platform}")

            self._audit(platform, video_path, result, privacy_status)
            if result.ok:
                self._posts_this_session += 1
            return result
        except Exception as exc:  # noqa: BLE001
            logger.exception("[SocialPublish] Publish failed for %s", platform)
            result = PublishResult(False, platform, str(exc))
            self._audit(platform, video_path, result, privacy_status)
            return result

    def default_privacy(self, platform: str) -> str:
        return self._default_privacy(platform)

    def _default_privacy(self, platform: str) -> str:
        default = str(getattr(self.settings, "default_privacy", None) or "private")
        if platform == "youtube":
            return default if default in {"private", "unlisted", "public"} else "private"
        return default

    def _audit(self, platform: str, video_path: Path, result: PublishResult, privacy: str) -> None:
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "platform": platform,
                "video": video_path.name,
                "privacy": privacy,
                "ok": result.ok,
                "video_id": result.video_id,
                "video_url": result.video_url,
                "message": result.message,
            }
            with open(self.audit_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
        except OSError as exc:
            logger.warning("[SocialPublish] Could not write audit log: %s", exc)

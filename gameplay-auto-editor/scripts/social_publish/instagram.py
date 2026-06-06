"""Instagram/Meta OAuth scaffold (requires Business/Creator account + Meta app)."""

from __future__ import annotations

import logging
import secrets
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from scripts.social_publish.oauth_flow import (
    build_auth_url_simple,
    exchange_code_for_tokens_confidential,
)
from scripts.social_publish.secure_storage import delete_token_bundle, load_token_bundle, save_token_bundle
from scripts.social_publish.settings import PlatformCredentials
from scripts.social_publish.youtube import ConnectionStatus, PublishResult

logger = logging.getLogger(__name__)

PLATFORM = "instagram"
AUTH_ENDPOINT = "https://www.facebook.com/v19.0/dialog/oauth"
TOKEN_ENDPOINT = "https://graph.facebook.com/v19.0/oauth/access_token"
SCOPES = "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement"


def get_status(credentials: PlatformCredentials) -> ConnectionStatus:
    if not credentials.client_id:
        return ConnectionStatus(
            connected=False,
            configured=False,
            message="Add META_APP_ID to .env and connect an Instagram Business/Creator account.",
        )
    bundle = load_token_bundle(PLATFORM)
    if not bundle:
        return ConnectionStatus(connected=False, configured=True, message="Not connected")
    return ConnectionStatus(
        connected=True,
        configured=True,
        account_label=str(bundle.get("account_label") or "Instagram account"),
        message="Connected",
    )


def connect(credentials: PlatformCredentials, *, timeout_seconds: int = 300) -> ConnectionStatus:
    if not credentials.client_id or not credentials.client_secret:
        raise RuntimeError("Meta app ID and secret are required.")

    state = secrets.token_urlsafe(32)
    code, redirect_uri = _capture_code(
        lambda redirect: build_auth_url_simple(
            authorize_endpoint=AUTH_ENDPOINT,
            client_id=credentials.client_id,
            redirect_uri=redirect,
            scope=SCOPES,
            state=state,
        ),
        expected_state=state,
        timeout_seconds=timeout_seconds,
    )
    tokens = exchange_code_for_tokens_confidential(
        token_endpoint=TOKEN_ENDPOINT,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret or "",
        code=code,
        redirect_uri=redirect_uri,
    )
    save_token_bundle(
        PLATFORM,
        {
            "access_token": tokens.access_token,
            "account_label": "Instagram account",
            "scope": tokens.scope,
        },
    )
    logger.info("[SocialAuth] Instagram/Meta connected")
    return get_status(credentials)


def disconnect() -> None:
    delete_token_bundle(PLATFORM)


def publish_clip(
    credentials: PlatformCredentials,
    *,
    video_path: Path,
    title: str,
    description: str,
    privacy_status: str = "public",
) -> PublishResult:
    if not load_token_bundle(PLATFORM):
        return PublishResult(False, PLATFORM, "Instagram is not connected.")
    if not video_path.exists():
        return PublishResult(False, PLATFORM, f"Clip not found: {video_path}")
    return PublishResult(
        False,
        PLATFORM,
        "Instagram Reels publishing requires an Instagram Business/Creator account linked to a Facebook Page, "
        "approved instagram_content_publish permissions, and a publicly accessible video URL. "
        "Meta's API does not accept direct local file uploads. Use YouTube for direct upload, "
        "or publish via Meta Business Suite.",
    )


def _capture_code(build_auth, expected_state: str, timeout_seconds: int) -> tuple[str, str]:
    result: dict[str, str | Exception] = {}
    event = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            params = urllib.parse.parse_qs(parsed.query)
            if params.get("error"):
                result["error"] = RuntimeError(params["error"][0])
            elif params.get("state", [""])[0] != expected_state:
                result["error"] = RuntimeError("OAuth state mismatch — request blocked for security.")
            else:
                result["code"] = params.get("code", [""])[0] or ""
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Signed in. Return to the app.")
            event.set()

        def log_message(self, format, *args):  # noqa: A003
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}/callback"
    threading.Thread(target=server.handle_request, daemon=True).start()
    webbrowser.open(build_auth(redirect_uri))
    event.wait(timeout=timeout_seconds)
    server.server_close()
    if "error" in result:
        raise result["error"]
    if not result.get("code"):
        raise RuntimeError("Instagram OAuth callback missing authorization code.")
    return str(result["code"]), redirect_uri

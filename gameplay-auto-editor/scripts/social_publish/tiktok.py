"""TikTok OAuth scaffold (requires approved TikTok developer app)."""

from __future__ import annotations

import logging
import secrets
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from scripts.social_publish.oauth_flow import build_auth_url, build_pkce_pair, exchange_code_for_tokens
from scripts.social_publish.secure_storage import delete_token_bundle, load_token_bundle, save_token_bundle
from scripts.social_publish.settings import PlatformCredentials
from scripts.social_publish.youtube import ConnectionStatus, PublishResult

logger = logging.getLogger(__name__)

PLATFORM = "tiktok"
AUTH_ENDPOINT = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_ENDPOINT = "https://open.tiktokapis.com/v2/oauth/token/"
SCOPES = "video.upload,video.publish,user.info.basic"


def get_status(credentials: PlatformCredentials) -> ConnectionStatus:
    if not credentials.client_id:
        return ConnectionStatus(
            connected=False,
            configured=False,
            message="Add TIKTOK_CLIENT_KEY to .env after TikTok developer approval.",
        )
    bundle = load_token_bundle(PLATFORM)
    if not bundle:
        return ConnectionStatus(connected=False, configured=True, message="Not connected")
    return ConnectionStatus(
        connected=True,
        configured=True,
        account_label=str(bundle.get("account_label") or "TikTok account"),
        message="Connected",
    )


def connect(credentials: PlatformCredentials, *, timeout_seconds: int = 300) -> ConnectionStatus:
    if not credentials.client_id or not credentials.client_secret:
        raise RuntimeError("TikTok client key and secret are required.")

    verifier, challenge = build_pkce_pair()
    state = secrets.token_urlsafe(32)
    code, redirect_uri = _capture_code(
        lambda redirect: build_auth_url(
            authorize_endpoint=AUTH_ENDPOINT,
            client_id=credentials.client_id,
            redirect_uri=redirect,
            scope=SCOPES,
            state=state,
            code_challenge=challenge,
        ),
        expected_state=state,
        timeout_seconds=timeout_seconds,
    )
    tokens = exchange_code_for_tokens(
        token_endpoint=TOKEN_ENDPOINT,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=verifier,
    )
    save_token_bundle(
        PLATFORM,
        {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "account_label": "TikTok account",
            "scope": tokens.scope,
        },
    )
    logger.info("[SocialAuth] TikTok connected")
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
    bundle = load_token_bundle(PLATFORM)
    if not bundle:
        return PublishResult(False, PLATFORM, "TikTok is not connected.")
    if not video_path.exists():
        return PublishResult(False, PLATFORM, f"Clip not found: {video_path}")

    # TikTok Content Posting API requires multi-step init/chunk upload and app audit.
    return PublishResult(
        False,
        PLATFORM,
        "TikTok direct posting requires an approved TikTok developer app. "
        "OAuth sign-in is ready; enable video.publish in your TikTok app to complete upload support.",
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
        raise RuntimeError("TikTok OAuth callback missing authorization code.")
    return str(result["code"]), redirect_uri

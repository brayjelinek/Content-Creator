"""YouTube OAuth and resumable video upload."""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from scripts.social_publish.oauth_flow import (
    OAuthTokens,
    build_auth_url,
    build_pkce_pair,
    exchange_code_for_tokens,
    refresh_access_token,
)
from scripts.social_publish.secure_storage import delete_token_bundle, load_token_bundle, save_token_bundle
from scripts.social_publish.settings import PlatformCredentials

logger = logging.getLogger(__name__)

PLATFORM = "youtube"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
CHANNELS_ENDPOINT = "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true"
UPLOAD_INIT_ENDPOINT = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
SCOPES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"


@dataclass
class ConnectionStatus:
    connected: bool
    account_label: str = ""
    configured: bool = False
    message: str = ""


@dataclass
class PublishResult:
    ok: bool
    platform: str
    message: str
    video_id: str | None = None
    video_url: str | None = None


def get_status(credentials: PlatformCredentials) -> ConnectionStatus:
    if not credentials.client_id:
        return ConnectionStatus(
            connected=False,
            configured=False,
            message="Add YOUTUBE_CLIENT_ID to .env (Google Cloud OAuth client).",
        )
    bundle = load_token_bundle(PLATFORM)
    if not bundle:
        return ConnectionStatus(connected=False, configured=True, message="Not connected")
    return ConnectionStatus(
        connected=True,
        configured=True,
        account_label=str(bundle.get("account_label") or "YouTube channel"),
        message="Connected",
    )


def connect(credentials: PlatformCredentials, *, timeout_seconds: int = 300) -> ConnectionStatus:
    if not credentials.client_id:
        raise RuntimeError("YouTube client ID is not configured.")

    verifier, challenge = build_pkce_pair()
    state = secrets.token_urlsafe(32)
    code, redirect_uri = _capture_authorization_code(
        build_auth=lambda redirect: build_auth_url(
            authorize_endpoint=AUTH_ENDPOINT,
            client_id=credentials.client_id,
            redirect_uri=redirect,
            scope=SCOPES,
            state=state,
            code_challenge=challenge,
            extra_params={"access_type": "offline", "prompt": "consent"},
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
    bundle = _bundle_from_tokens(tokens)
    bundle["account_label"] = _fetch_channel_label(tokens.access_token)
    save_token_bundle(PLATFORM, bundle)
    logger.info("[SocialAuth] YouTube connected for %s", bundle["account_label"])
    return get_status(credentials)


def disconnect() -> None:
    delete_token_bundle(PLATFORM)


def publish_clip(
    credentials: PlatformCredentials,
    *,
    video_path: Path,
    title: str,
    description: str,
    privacy_status: str = "private",
) -> PublishResult:
    if not video_path.exists():
        return PublishResult(False, PLATFORM, f"Clip not found: {video_path}")

    access_token = _valid_access_token(credentials)
    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "categoryId": "20",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }
    init_request = urllib.request.Request(
        UPLOAD_INIT_ENDPOINT,
        data=json.dumps(metadata).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(video_path.stat().st_size),
        },
        method="POST",
    )
    with urllib.request.urlopen(init_request, timeout=60) as response:
        upload_url = response.headers.get("Location")
    if not upload_url:
        return PublishResult(False, PLATFORM, "YouTube upload initialization failed.")

    with video_path.open("rb") as handle:
        upload_request = urllib.request.Request(
            upload_url,
            data=handle.read(),
            headers={"Content-Type": "video/mp4"},
            method="PUT",
        )
        with urllib.request.urlopen(upload_request, timeout=600) as response:
            payload = json.loads(response.read().decode("utf-8"))

    video_id = str(payload.get("id") or "")
    if not video_id:
        return PublishResult(False, PLATFORM, "YouTube upload completed without a video ID.")
    url = f"https://www.youtube.com/shorts/{video_id}"
    return PublishResult(True, PLATFORM, "Uploaded to YouTube.", video_id=video_id, video_url=url)


def _capture_authorization_code(
    *,
    build_auth,
    expected_state: str,
    timeout_seconds: int,
) -> tuple[str, str]:
    result: dict[str, str | Exception] = {}
    event = threading.Event()

    class CallbackHandler(BaseHTTPRequestHandler):
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
            elif not params.get("code"):
                result["error"] = RuntimeError("OAuth callback missing authorization code.")
            else:
                result["code"] = params["code"][0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Sign-in complete.</h2>"
                b"<p>You can close this window and return to Gameplay Auto Editor.</p></body></html>"
            )
            event.set()

        def log_message(self, format, *args):  # noqa: A003
            return

    server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}/callback"
    auth_url = build_auth(redirect_uri)

    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    logger.info("[SocialAuth] Opening browser for YouTube OAuth consent.")
    webbrowser.open(auth_url)

    if not event.wait(timeout=timeout_seconds):
        result["error"] = RuntimeError("OAuth sign-in timed out.")

    server.server_close()
    if "error" in result:
        raise result["error"]
    return str(result["code"]), redirect_uri


def _valid_access_token(credentials: PlatformCredentials) -> str:
    bundle = load_token_bundle(PLATFORM)
    if not bundle:
        raise RuntimeError("YouTube is not connected.")

    expires_at = float(bundle.get("expires_at") or 0)
    if bundle.get("access_token") and expires_at > time.time() + 60:
        return str(bundle["access_token"])

    refresh = str(bundle.get("refresh_token") or "")
    if not refresh:
        raise RuntimeError("YouTube session expired. Connect again.")

    tokens = refresh_access_token(
        token_endpoint=TOKEN_ENDPOINT,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
        refresh_token=refresh,
    )
    updated = _bundle_from_tokens(tokens, previous=bundle)
    save_token_bundle(PLATFORM, updated)
    return str(updated["access_token"])


def _bundle_from_tokens(tokens: OAuthTokens, previous: dict | None = None) -> dict:
    expires_at = time.time() + float(tokens.expires_in or 3600)
    refresh_token = tokens.refresh_token or (previous or {}).get("refresh_token")
    return {
        "access_token": tokens.access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "scope": tokens.scope,
        "account_label": (previous or {}).get("account_label", ""),
    }


def _fetch_channel_label(access_token: str) -> str:
    request = urllib.request.Request(
        CHANNELS_ENDPOINT,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    items = payload.get("items") or []
    if not items:
        return "YouTube channel"
    snippet = items[0].get("snippet") or {}
    return str(snippet.get("title") or snippet.get("customUrl") or "YouTube channel")

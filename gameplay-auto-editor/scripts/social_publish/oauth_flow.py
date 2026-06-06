"""OAuth 2.0 authorization code flow with PKCE and CSRF state validation."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

import urllib.request

logger = logging.getLogger(__name__)


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    token_type: str = "Bearer"
    scope: str | None = None
    raw: dict | None = None


@dataclass
class OAuthStart:
    auth_url: str
    redirect_uri: str
    state: str
    code_verifier: str


def build_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def build_auth_url_simple(
    *,
    authorize_endpoint: str,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
    extra_params: dict[str, str] | None = None,
) -> str:
    """Build OAuth authorize URL without PKCE (Meta/Facebook Login)."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
    }
    if extra_params:
        params.update(extra_params)
    return f"{authorize_endpoint}?{urllib.parse.urlencode(params)}"


def build_auth_url(
    *,
    authorize_endpoint: str,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
    code_challenge: str,
    extra_params: dict[str, str] | None = None,
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if extra_params:
        params.update(extra_params)
    return f"{authorize_endpoint}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens_confidential(
    *,
    token_endpoint: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    method: str = "GET",
) -> OAuthTokens:
    """Exchange authorization code using client secret (no PKCE)."""
    params = {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if method.upper() == "GET":
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            f"{token_endpoint}?{query}",
            headers={"Accept": "application/json"},
            method="GET",
        )
    else:
        body = urllib.parse.urlencode(params).encode("utf-8")
        request = urllib.request.Request(
            token_endpoint,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            method="POST",
        )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = json_load(response.read().decode("utf-8"))

    access_token = str(raw.get("access_token") or "")
    if not access_token:
        raise RuntimeError("OAuth token response missing access_token")
    return OAuthTokens(
        access_token=access_token,
        refresh_token=raw.get("refresh_token"),
        expires_in=int(raw["expires_in"]) if raw.get("expires_in") else None,
        token_type=str(raw.get("token_type") or "Bearer"),
        scope=raw.get("scope"),
        raw=raw,
    )


def exchange_code_for_tokens(
    *,
    token_endpoint: str,
    client_id: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    client_secret: str | None = None,
    extra_data: dict[str, str] | None = None,
) -> OAuthTokens:
    """Exchange authorization code for tokens using PKCE."""
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    if extra_data:
        payload.update(extra_data)

    body = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        token_endpoint,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = json_load(response.read().decode("utf-8"))

    access_token = str(raw.get("access_token") or "")
    if not access_token:
        raise RuntimeError("OAuth token response missing access_token")
    return OAuthTokens(
        access_token=access_token,
        refresh_token=raw.get("refresh_token"),
        expires_in=int(raw["expires_in"]) if raw.get("expires_in") else None,
        token_type=str(raw.get("token_type") or "Bearer"),
        scope=raw.get("scope"),
        raw=raw,
    )


def refresh_access_token(
    *,
    token_endpoint: str,
    client_id: str,
    refresh_token: str,
    client_secret: str | None = None,
    extra_data: dict[str, str] | None = None,
) -> OAuthTokens:
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    if extra_data:
        payload.update(extra_data)

    body = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        token_endpoint,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = json_load(response.read().decode("utf-8"))

    access_token = str(raw.get("access_token") or "")
    if not access_token:
        raise RuntimeError("OAuth refresh response missing access_token")
    return OAuthTokens(
        access_token=access_token,
        refresh_token=raw.get("refresh_token") or refresh_token,
        expires_in=int(raw["expires_in"]) if raw.get("expires_in") else None,
        token_type=str(raw.get("token_type") or "Bearer"),
        scope=raw.get("scope"),
        raw=raw,
    )


def run_local_oauth_capture(
    *,
    auth_url: str,
    expected_state: str,
    timeout_seconds: int = 300,
    open_browser: Callable[[str], None] | None = None,
) -> str:
    """Start localhost callback server, open browser, return authorization code."""
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
                result["error"] = RuntimeError("OAuth state mismatch — possible CSRF attempt")
            elif not params.get("code"):
                result["error"] = RuntimeError("OAuth callback missing authorization code")
            else:
                result["code"] = params["code"][0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authorization complete.</h2>"
                b"<p>You can close this window and return to Gameplay Auto Editor.</p></body></html>"
            )
            event.set()

        def log_message(self, format, *args):  # noqa: A003
            return

    server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    final_auth_url = auth_url.replace("REDIRECT_URI_PLACEHOLDER", urllib.parse.quote(redirect_uri, safe=""))

    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    opener = open_browser or webbrowser.open
    logger.info("[SocialAuth] Opening browser for OAuth consent (localhost:%s)", port)
    opener(final_auth_url.replace(urllib.parse.quote("REDIRECT_URI_PLACEHOLDER", safe=""), redirect_uri))

    if not event.wait(timeout=timeout_seconds):
        result["error"] = RuntimeError("OAuth sign-in timed out")

    server.server_close()

    if "error" in result:
        raise result["error"]
    return str(result["code"])


def json_load(raw: str) -> dict:
    import json

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected OAuth JSON payload")
    return data

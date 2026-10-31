"""Serve the simulator under its existing CloudFront path and ticker-info login.

The local development entrypoint remains app.main:app. This hosted entrypoint
requires an explicit authentication service and never reads or copies its
signing secrets or passwords.
"""

import hashlib
import os
import time
from pathlib import Path

import httpx
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

from app.main import app


class AuthenticationProbe:
    def __init__(self, session_url: str) -> None:
        if not session_url:
            raise RuntimeError("AUTH_SESSION_URL is required for the hosted application")
        self.session_url = session_url
        self.cache: dict[str, tuple[float, bool]] = {}

    async def authenticated(self, headers: Headers) -> bool | None:
        cookie = headers.get("cookie", "")
        authorization = headers.get("authorization", "")
        key = hashlib.sha256(f"{cookie}\0{authorization}".encode()).hexdigest()
        now = time.monotonic()
        cached = self.cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
        forwarded = {"Accept": "application/json"}
        if cookie:
            forwarded["Cookie"] = cookie
        if authorization:
            forwarded["Authorization"] = authorization
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(self.session_url, headers=forwarded)
            if response.status_code == 401:
                result = False
            else:
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    return None
                result = payload.get("authenticated") is True
        except (httpx.HTTPError, ValueError):
            return None
        if len(self.cache) >= 512:
            self.cache.clear()
        self.cache[key] = (now + 10, result)
        return result


class HostedApplication:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.base_path = os.environ.get("BASE_PATH", "/price-generator").rstrip("/")
        self.authentication = AuthenticationProbe(os.environ.get("AUTH_SESSION_URL", "").strip())
        self.static = StaticFiles(directory=os.environ.get("STATIC_DIR", root / "frontend/dist/frontend/browser"), html=True)
        self.login_page = Path(os.environ.get("LOGIN_PAGE_PATH", root / "deploy/login.html"))
        self.release = os.environ.get("RELEASE_SHA", "development")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        path = scope["path"]
        if path == self.base_path:
            await RedirectResponse(self.base_path + "/", status_code=308)(scope, receive, send)
            return
        if not path.startswith(self.base_path + "/"):
            await JSONResponse({"error": "Unknown route"}, status_code=404)(scope, receive, send)
            return
        relative = path[len(self.base_path):]
        if relative == "/health":
            await JSONResponse({"ok": True, "release": self.release}, headers={"Cache-Control": "no-store"})(scope, receive, send)
            return
        authenticated = await self.authentication.authenticated(Headers(scope=scope))
        if authenticated is not True:
            if authenticated is False and relative == "/":
                response = FileResponse(self.login_page, media_type="text/html", headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"})
            else:
                response = JSONResponse(
                    {"error": "Sign in with your ticker info account to continue." if authenticated is False else "Ticker info sign-in is temporarily unavailable."},
                    status_code=401 if authenticated is False else 503,
                    headers={"Cache-Control": "no-store"},
                )
            await response(scope, receive, send)
            return
        routed_scope = {
            **scope,
            "path": relative,
            "raw_path": relative.encode(),
            "root_path": scope.get("root_path", "") + self.base_path,
        }
        if relative.startswith("/api/") or relative in {"/docs", "/openapi.json", "/redoc"}:
            await app(routed_scope, receive, send)
        else:
            try:
                await self.static(routed_scope, receive, send)
            except HTTPException as error:
                await JSONResponse({"error": error.detail}, status_code=error.status_code)(scope, receive, send)


application = HostedApplication()

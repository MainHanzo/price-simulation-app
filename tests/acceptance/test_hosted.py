"""Hosted-path and existing ticker-info sign-in contract over real HTTP."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest

from conftest import running_server


@pytest.fixture
def hosted(tmp_path: Path) -> Iterator[httpx.Client]:
    class AuthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            authenticated = self.headers.get("Cookie") == "ticker_session=allowed" or self.headers.get("Authorization") == "Bearer allowed"
            if self.headers.get("Cookie") == "ticker_session=unavailable":
                self.send_response(503)
                self.end_headers()
                return
            body = json.dumps({"auth_required": True, "authenticated": authenticated}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    (tmp_path / "index.html").write_text("<h1>Hosted simulator</h1>")
    (tmp_path / "main.js").write_text("/* hosted asset */")
    auth = ThreadingHTTPServer(("127.0.0.1", 0), AuthHandler)
    thread = threading.Thread(target=auth.serve_forever, daemon=True)
    thread.start()
    try:
        with running_server(None, "app.hosted:application", {
            "BASE_PATH": "/price-generator",
            "STATIC_DIR": str(tmp_path),
            "LOGIN_PAGE_PATH": str(Path(__file__).resolve().parents[2] / "deploy/login.html"),
            "AUTH_SESSION_URL": f"http://127.0.0.1:{auth.server_port}/v1/auth/session",
            "RELEASE_SHA": "acceptance-release",
        }) as client:
            yield client
    finally:
        auth.shutdown()
        auth.server_close()
        thread.join(timeout=5)


def test_hosted_page_keeps_existing_sign_in(hosted: httpx.Client) -> None:
    response = hosted.get("/price-generator/")
    assert response.status_code == 200
    assert "ticker info account" in response.text
    assert "no-store" in response.headers["cache-control"]
    assert hosted.get("/price-generator/main.js").status_code == 401
    assert hosted.get("/price-generator/api/orderbook/AAPL").status_code == 401
    assert hosted.get("/price-generator/api/orderbook/AAPL/stream").status_code == 401
    assert hosted.get("/api/orderbook/AAPL").status_code == 404


@pytest.mark.parametrize("headers", [{"Cookie": "ticker_session=allowed"}, {"Authorization": "Bearer allowed"}])
def test_authenticated_hosted_assets_and_stream(hosted: httpx.Client, headers: dict[str, str]) -> None:
    assert hosted.get("/price-generator/", headers=headers).text == "<h1>Hosted simulator</h1>"
    assert hosted.get("/price-generator/main.js", headers=headers).status_code == 200
    assert hosted.get("/price-generator/missing.js", headers=headers).status_code == 404
    snapshot = hosted.get("/price-generator/api/orderbook/AAPL", headers=headers)
    assert snapshot.status_code == 200
    assert len(snapshot.json()["bids"]) == 10
    with hosted.stream("GET", "/price-generator/api/orderbook/AAPL/stream", headers=headers) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("data: "):
                assert json.loads(line[6:])["ticker"] == "AAPL"
                break


def test_hosted_health_redirect_and_unavailable_auth(hosted: httpx.Client) -> None:
    health = hosted.get("/price-generator/health")
    assert health.status_code == 200
    assert health.json() == {"ok": True, "release": "acceptance-release"}
    redirect = hosted.get("/price-generator")
    assert redirect.status_code == 308
    assert redirect.headers["location"] == "/price-generator/"
    failure = hosted.get("/price-generator/api/config", headers={"Cookie": "ticker_session=unavailable"})
    assert failure.status_code == 503

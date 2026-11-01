"""Serve the Price Generator UI and its in-process simulation API."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from price_generator.order_book import SimulatedOrderBook

from price_generator import (
    AssetClass,
    BAR_INTERVAL_SECONDS,
    SIMULATION_MODEL_LABELS,
    SimulationModel,
    create_simulator,
)


WEB_ROOT = Path(__file__).parent / "web"
MAX_CHART_BARS = 240
BASE_PATH = os.environ.get("BASE_PATH", "").rstrip("/")
AUTH_SESSION_URL = os.environ.get("AUTH_SESSION_URL", "").strip()
RELEASE_SHA = os.environ.get("RELEASE_SHA", "development")


class AuthenticationProbe:
    """Validate browser sessions through ticker-info's existing auth API."""

    def __init__(self, session_url: str, cache_seconds: float = 10.0) -> None:
        self._session_url = session_url
        self._cache_seconds = cache_seconds
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, bool]] = {}

    def authenticated(self, headers) -> bool | None:
        if not self._session_url:
            return True

        cookie = headers.get("Cookie", "")
        authorization = headers.get("Authorization", "")
        cache_key = hashlib.sha256(f"{cookie}\0{authorization}".encode("utf-8")).hexdigest()
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and cached[0] > now:
                return cached[1]
            self._cache.pop(cache_key, None)

        forwarded_headers = {"Accept": "application/json"}
        if cookie:
            forwarded_headers["Cookie"] = cookie
        if authorization:
            forwarded_headers["Authorization"] = authorization
        request = Request(self._session_url, headers=forwarded_headers)
        try:
            with urlopen(request, timeout=5) as response:
                result = json.loads(response.read())
        except (URLError, TimeoutError, OSError, ValueError):
            return None
        if not isinstance(result, dict):
            return None

        authorized = not result.get("auth_required", True) or result.get("authenticated") is True
        with self._lock:
            if len(self._cache) > 512:
                self._cache.clear()
            self._cache[cache_key] = (now + self._cache_seconds, authorized)
        return authorized


authentication = AuthenticationProbe(AUTH_SESSION_URL)


class SimulationSession:
    """One local browser session backed by the Python simulation engine."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._simulator = None
        self._running = False
        self._last_wall_time: float | None = None
        self._run_id = 0
        self._history: deque = deque(maxlen=MAX_CHART_BARS)
        self._pending_bars: deque = deque(maxlen=1_000)
        self._current_bar = None
        self._asset_class: str | None = None
        self._bar_interval: str | None = None
        self._start_price: float | None = None
        self._simulation_model: str | None = None
        self._order_book: SimulatedOrderBook | None = None

    def start(self, asset_class: str, bar_interval: str, simulation_model: str) -> dict:
        asset = AssetClass(asset_class)
        model = SimulationModel(simulation_model)
        if bar_interval not in BAR_INTERVAL_SECONDS:
            raise ValueError("Choose one of the supported bar intervals")

        with self._lock:
            self._simulator = create_simulator(asset, bar_interval, simulation_model=model)
            self._running = True
            self._last_wall_time = time.monotonic()
            self._run_id += 1
            self._order_book = SimulatedOrderBook(self._run_id)
            self._history.clear()
            self._pending_bars.clear()
            self._current_bar = self._simulator.current_bar
            self._asset_class = asset.value
            self._bar_interval = bar_interval
            self._start_price = self._simulator.profile.starting_price
            self._simulation_model = model.value
            return self._snapshot_locked(include_history=True)

    def stop(self) -> dict:
        with self._lock:
            self._advance_locked()
            self._running = False
            self._last_wall_time = None
            return self._snapshot_locked()

    def state(self, *, include_history: bool = False) -> dict:
        with self._lock:
            self._advance_locked()
            return self._snapshot_locked(include_history=include_history)

    def order_book(self) -> dict | None:
        with self._lock:
            self._advance_locked()
            return self._book_snapshot_locked()

    def _book_snapshot_locked(self) -> dict | None:
        if self._current_bar is None or self._order_book is None:
            return None
        bar = self._current_bar
        return self._order_book.update(bar.close, bar.start_simulated_seconds + bar.elapsed_simulated_seconds, self._running)

    def _advance_locked(self) -> None:
        if not self._running or self._simulator is None:
            return
        now = time.monotonic()
        previous = self._last_wall_time if self._last_wall_time is not None else now
        self._last_wall_time = now
        result = self._simulator.advance_wall_time(max(0.0, now - previous))
        for bar in result.completed_bars:
            self._history.append(bar)
            self._pending_bars.append(bar)
        self._current_bar = result.forming_bar

    def _snapshot_locked(self, *, include_history: bool = False) -> dict:
        closed_bars = [asdict(bar) for bar in self._pending_bars]
        self._pending_bars.clear()
        payload = {
            "run_id": self._run_id,
            "running": self._running,
            "asset_class": self._asset_class,
            "bar_interval": self._bar_interval,
            "simulation_model": self._simulation_model,
            "model_label": (
                SIMULATION_MODEL_LABELS[SimulationModel(self._simulation_model)]
                if self._simulation_model
                else None
            ),
            "start_price": self._start_price,
            "current_bar": asdict(self._current_bar) if self._current_bar else None,
            "closed_bars": closed_bars,
            "order_book": self._book_snapshot_locked(),
        }
        if include_history:
            payload["history"] = [asdict(bar) for bar in self._history]
        return payload


session = SimulationSession()


class RequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if BASE_PATH and parsed.path == BASE_PATH:
            self.send_response(308)
            self.send_header("Location", f"{BASE_PATH}/")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        path = self._application_path(parsed.path)
        if path is None:
            self._send_json(404, {"error": "Unknown route"})
            return
        if path == "/health":
            self._send_json(200, {"ok": True, "release": RELEASE_SHA})
            return
        if not self._require_authentication(path):
            return
        if path == "/api/state":
            include_history = parse_qs(parsed.query).get("history") == ["1"]
            self._send_json(200, session.state(include_history=include_history))
            return
        if path == "/api/orderbook":
            self._send_json(200, session.order_book())
            return
        if path.startswith("/api/"):
            self._send_json(404, {"error": "Unknown API route"})
            return
        self.path = urlunsplit(("", "", path, parsed.query, ""))
        super().do_GET()

    def do_HEAD(self) -> None:
        parsed = urlsplit(self.path)
        if BASE_PATH and parsed.path == BASE_PATH:
            self.send_response(308)
            self.send_header("Location", f"{BASE_PATH}/")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        path = self._application_path(parsed.path)
        if path is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b'{"ok":true}')))
            self.end_headers()
            return
        authenticated = authentication.authenticated(self.headers)
        if authenticated is not True:
            self.send_response(401 if authenticated is False else 503)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.path = urlunsplit(("", "", path, parsed.query, ""))
        super().do_HEAD()

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        path = self._application_path(parsed.path)
        if path not in {"/api/start", "/api/stop"}:
            self._send_json(404, {"error": "Unknown API route"})
            return
        if not self._require_authentication(path):
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length) or b"{}")
            if path == "/api/start":
                result = session.start(
                    str(payload.get("asset_class", "")),
                    str(payload.get("bar_interval", "")),
                    str(payload.get("simulation_model", SimulationModel.REGIME_SWITCHING.value)),
                )
                self._send_json(200, result)
                return
            if path == "/api/stop":
                self._send_json(200, session.stop())
                return
            self._send_json(404, {"error": "Unknown API route"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": str(exc) or "Invalid request"})

    def _application_path(self, path: str) -> str | None:
        if not BASE_PATH:
            return path
        if path == BASE_PATH:
            return "/"
        if path.startswith(f"{BASE_PATH}/"):
            return path[len(BASE_PATH) :]
        return None

    def _require_authentication(self, path: str) -> bool:
        authenticated = authentication.authenticated(self.headers)
        if authenticated is True:
            return True
        if authenticated is False and path == "/":
            self._send_login_page()
            return False
        if authenticated is False:
            self._send_json(401, {"error": "Sign in with your ticker info account to continue."})
            return False
        self._send_json(503, {"error": "Ticker info sign-in is temporarily unavailable."})
        return False

    def _send_login_page(self) -> None:
        page = (WEB_ROOT / "login.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(page)

    def _send_json(self, status: int, payload: object) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    if os.environ.get("REQUIRE_AUTH") == "1" and not AUTH_SESSION_URL:
        raise RuntimeError("AUTH_SESSION_URL is required for the hosted simulator")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), RequestHandler)
    print(f"Price Generator running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPrice Generator stopped")
    finally:
        server.server_close()

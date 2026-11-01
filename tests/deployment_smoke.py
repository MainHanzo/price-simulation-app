"""External HTTP acceptance checks for a staged or live hosted release.

Run on the deployment host with --auth-container quant-api to reuse its
existing service token for the check. Credentials are never printed or saved.
This file also runs on the host's Python 3.9 without application imports.
"""

import argparse
import json
import os
import subprocess
from typing import Any, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def check(base_url: str, release: str, token: str) -> None:
    import time

    def request(path: str, authenticated: bool = False, payload: Optional[dict[str, Any]] = None) -> tuple[int, bytes]:
        headers = {"Authorization": "Bearer " + token} if authenticated else {}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()
        try:
            with urlopen(Request(base_url + path, headers=headers, data=data), timeout=10) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()

    status, body = request("/health")
    assert status == 200 and json.loads(body) == {"ok": True, "release": release}
    status, body = request("/")
    assert status == 200 and b"ticker info account" in body
    assert request("/api/state")[0] == 401
    assert request("/api/orderbook")[0] == 401
    status, body = request("/", True)
    assert status == 200 and b"Price Generator" in body and b'id="assetClass"' in body
    assert b'id="ticker-input"' not in body and b"AAPL" not in body
    status, body = request("/api/start", True, {"asset_class": "stocks", "bar_interval": "1m", "simulation_model": "regime_switching"})
    assert status == 200
    initial = json.loads(body)
    time.sleep(1.2)
    status, body = request("/api/state", True)
    state = json.loads(body)
    book = state["order_book"]
    assert status == 200 and state["current_bar"]["is_synthetic"] is True
    assert len(book["bids"]) == len(book["asks"]) == 10
    assert book["reference_price"] == state["current_bar"]["close"]
    assert book["bids"][0]["price"] < book["reference_price"] < book["asks"][0]["price"]
    assert book["sequence"] > initial["order_book"]["sequence"]
    status, body = request("/api/stop", True, {})
    assert status == 200
    stopped = json.loads(body)
    assert stopped["running"] is False and stopped["order_book"]["status"] == "stopped"
    status, body = request("/api/orderbook", True)
    assert status == 200 and json.loads(body) == stopped["order_book"]
    assert request("/api/orderbook/AAPL", True)[0] == 404
    print("Market Lab verified: original UI, shared login, anonymous simulation, aligned depth, Start/Stop.")


def service_token(container: Optional[str]) -> str:
    token = os.environ.get("PRICE_SMOKE_TOKEN", "")
    if not token and container:
        inspected = json.loads(subprocess.check_output(["docker", "inspect", container]))
        values = dict(item.split("=", 1) for item in inspected[0]["Config"]["Env"] if "=" in item)
        entries = values.get("AUTH_API_TOKENS", "").split(",")
        for entry in entries:
            if ":" in entry:
                token = entry.split(":", 1)[1].strip()
                if token:
                    break
    if not token:
        raise SystemExit("Supply PRICE_SMOKE_TOKEN or a container with an existing AUTH_API_TOKENS value")
    return token


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--auth-container")
    args = parser.parse_args()
    check(args.base_url.rstrip("/"), args.release, service_token(args.auth_container))

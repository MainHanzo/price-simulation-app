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
    def request(path: str, authenticated: bool = False) -> tuple[int, bytes]:
        headers = {"Authorization": "Bearer " + token} if authenticated else {}
        try:
            with urlopen(Request(base_url + path, headers=headers), timeout=10) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()

    status, body = request("/health")
    assert status == 200 and json.loads(body) == {"ok": True, "release": release}
    status, body = request("/")
    assert status == 200 and b"ticker info account" in body
    assert request("/api/orderbook/AAPL")[0] == 401
    assert request("/api/orderbook/AAPL/stream")[0] == 401
    status, body = request("/", True)
    assert status == 200 and b"<app-root>" in body and b'/price-generator/' in body
    status, body = request("/api/orderbook/AAPL", True)
    assert status == 200
    book: dict[str, Any] = json.loads(body)
    assert len(book["bids"]) == len(book["asks"]) == 10
    assert book["bids"][0]["price"] < book["reference_price"] < book["asks"][0]["price"]
    with urlopen(Request(base_url + "/api/orderbook/AAPL/stream", headers={"Authorization": "Bearer " + token}), timeout=10) as response:
        assert response.headers["Content-Type"].startswith("text/event-stream")
        received = []
        while len(received) < 2:
            line = response.readline().decode()
            assert line, "Stream ended before two snapshots"
            if line.startswith("data: "):
                received.append(json.loads(line[6:]))
        assert received[1]["sequence"] > received[0]["sequence"]
        assert received[1]["ts"] > received[0]["ts"]
    print("Hosted release verified: health, login, denied anonymous API, authenticated UI/book, live SSE.")


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

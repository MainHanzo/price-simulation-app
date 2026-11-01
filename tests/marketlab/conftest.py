"""Run the restored anonymous simulator as an executable, never via app imports."""

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest


@pytest.fixture(params=["", "/price-generator"])
def marketlab_server(request: pytest.FixtureRequest) -> Iterator[tuple[httpx.Client, str]]:
    prefix = str(request.param)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env = {**os.environ, "HOST": "127.0.0.1", "PORT": str(port), "BASE_PATH": prefix, "AUTH_SESSION_URL": "", "REQUIRE_AUTH": "0"}
    process = subprocess.Popen(
        [sys.executable, "server.py"], cwd=Path(__file__).resolve().parents[2],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=8) as client:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    pytest.fail(f"Simulator exited: {process.stderr.read() if process.stderr else ''}")
                try:
                    if client.get(prefix + "/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                if time.monotonic() > deadline:
                    pytest.fail("Simulator did not start")
                time.sleep(0.05)
            yield client, prefix
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

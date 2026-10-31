"""Acceptance tests launch the executable and use HTTP, never application imports."""

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest


@contextmanager
def running_server(
    simulation_dt: str | None,
    entrypoint: str = "app.main:app",
    extra_env: dict[str, str] | None = None,
) -> Iterator[httpx.Client]:
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env = os.environ.copy()
    env.pop("SIMULATION_DT", None)
    if simulation_dt is not None:
        env["SIMULATION_DT"] = simulation_dt
    env.update(extra_env or {})
    with subprocess.Popen(
        [sys.executable, "-m", "uvicorn", entrypoint, "--host", "127.0.0.1", "--port", str(port)],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=8) as client:
                deadline = time.monotonic() + 10
                while True:
                    if process.poll() is not None:
                        pytest.fail(f"Server exited during startup: {process.stderr.read() if process.stderr else ''}")
                    try:
                        ready_path = f"{env.get('BASE_PATH', '')}/health" if entrypoint == "app.hosted:application" else "/api/config"
                        if client.get(ready_path).status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if time.monotonic() > deadline:
                        pytest.fail("Server did not become ready")
                    time.sleep(0.05)
                yield client
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


@pytest.fixture
def market() -> Iterator[httpx.Client]:
    with running_server("2024-01-02T11:30:00-05:00") as client:
        yield client

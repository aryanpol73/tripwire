"""Run a scenario's app in a background thread, for tests and the eval harness."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import uvicorn

from evilweb.app import create_app


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def serve(scenario_id: str) -> Iterator[str]:
    """Yield the base URL of a fresh, running scenario; stop it afterwards."""
    with serve_app(create_app(scenario_id), scenario_id) as url:
        yield url


@contextmanager
def serve_app(app, label: str = "app") -> Iterator[str]:
    """Serve any ASGI app on a free local port (red-team pages, unseen layouts)."""
    scenario_id = label
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError(f"sandbox server for {scenario_id} did not start")
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)

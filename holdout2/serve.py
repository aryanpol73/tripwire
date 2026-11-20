"""Serve all nine hold-out v2 cases on 127.0.0.1:8301-8309 until Ctrl+C.

uv run python -m holdout2.serve
uv run tripwire eval --holdout holdout2/manifest.json   (in a second terminal)
"""

from __future__ import annotations

import threading
import time

import uvicorn

from holdout2.app import create_app
from holdout2.design import CASES


def start_all() -> list[uvicorn.Server]:
    servers = []
    for case in CASES:
        config = uvicorn.Config(
            create_app(case), host="127.0.0.1", port=case.port, log_level="warning"
        )
        server = uvicorn.Server(config)
        threading.Thread(target=server.run, daemon=True).start()
        servers.append(server)
    deadline = time.monotonic() + 15
    while not all(s.started for s in servers):
        if time.monotonic() > deadline:
            raise RuntimeError("hold-out servers did not start (ports 8301-8309 in use?)")
        time.sleep(0.05)
    return servers


def main() -> None:
    servers = start_all()
    for case in CASES:
        print(f"{case.id:<36} http://127.0.0.1:{case.port}/")
    print("All nine hold-out v2 cases are up. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for s in servers:
            s.should_exit = True


if __name__ == "__main__":
    main()

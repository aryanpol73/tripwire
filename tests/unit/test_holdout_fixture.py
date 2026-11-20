"""The hold-out fixture itself: pages render offline and the manifest meets the contract.

These tests never run the walker or the detectors: the hold-out is scored once, by the
backend, with `tripwire eval --holdout holdout/manifest.json`.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from holdout.app import create_app
from holdout.design import CASES
from tripwire.eval.holdout import Holdout

MANIFEST = Path(__file__).resolve().parents[2] / "holdout" / "manifest.json"
EXTERNAL = re.compile(r"""(src|href|action)\s*=\s*["']?(https?:)?//""", re.IGNORECASE)
START = {
    "grocery": ["/", "/item/BAN6", "/basket", "/checkout", "/review"],
    "streaming": [
        "/",
        "/plans",
        "/join",
        "/join/review",
        "/account",
        "/account/subscription",
        "/account/cancel/0",
    ],
    "magazine": ["/", "/section/culture", "/story/night-markets"],
}


def test_manifest_meets_the_holdout_contract():
    suite = Holdout.model_validate_json(MANIFEST.read_text(encoding="utf-8"))
    assert len(suite.cases) == 9
    assert len({c.skin for c in suite.cases}) == 3
    assert len({c.layout for c in suite.cases}) == 3


def test_manifest_and_servers_agree_on_ports():
    suite = Holdout.model_validate_json(MANIFEST.read_text(encoding="utf-8"))
    served = {c.id: f"http://127.0.0.1:{c.port}/" for c in CASES}
    assert {c.id: c.source.url for c in suite.cases} == served


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_every_page_renders_offline(case):
    client = TestClient(create_app(case))
    if case.layout == "grocery":
        client.post("/basket/add", data={"sku": "BAN6"})
    for path in START[case.layout]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert not EXTERNAL.search(response.text), path
        assert "Privacy choices" in response.text  # the consent banner is on every page

"""D-072: the gate-3 unseen layouts work end to end over plain HTTP (no browser, no model),
and the eval gates them while the earlier layouts are only reported."""

import re

from fastapi.testclient import TestClient

from tripwire.eval.llm_eval import RunResult, all_targets, summarize
from unseen.sites_v2 import LAYOUTS_V2, fresco, ledgerline, pagewise

LAYOUT = {layout.id: layout for layout in LAYOUTS_V2}


def test_pagewise_join_then_stop_membership():
    c = TestClient(pagewise())
    assert c.post("/join", data={"email": "a@b.test", "first_name": "T"}).url.path == "/shelf"
    for path in ("/account", "/account/plan", "/account/plan/change", "/account/plan/stop"):
        assert c.get(path).status_code == 200, path
    end = c.post("/account/plan/stop/confirm", data={"ack": "on"})
    assert LAYOUT["pagewise-books"].left_text.search(end.text)


def test_fresco_checkout_reaches_the_pay_button():
    c = TestClient(fresco())
    c.post("/basket/add", data={"item": "bananas"})
    c.post("/checkout/details", data={})
    page = c.post("/checkout/slot", data={"slot": "am"})
    button = re.search(r"<button[^>]*>([^<]*now)</button>", page.text)[1]
    assert LAYOUT["fresco-grocery"].pay_control.search(button)


def test_ledgerline_join_then_unsubscribe():
    c = TestClient(ledgerline())
    assert c.post("/brief", data={"email": "a@b.test"}).url.path == "/brief/welcome"
    assert c.post("/subscriptions", data={"email": "a@b.test"}).url.path == "/subscriptions/list"
    done = c.post("/subscriptions/morning-brief/leave", data={})
    assert LAYOUT["ledgerline-news"].left_text.search(done.text)


def test_unseen_v2_is_gated_and_the_earlier_layouts_are_only_reported():
    targets = all_targets({"unseen", "dev"})
    unseen = {t.id for t in targets if t.group == "unseen"}
    dev = {t.id for t in targets if t.group == "dev"}
    assert len(unseen) == 6 and all(t.split("--")[0] in LAYOUT for t in unseen)
    assert len(dev) == 6 and "streamly-video--sign_up_and_leave" in dev

    def result(t, completed):
        return RunResult(t, "dev" if t in dev else "unseen", completed, "", "completed", 1, 0,
                         500_000, "")  # fmt: skip

    rows = [result(t, True) for t in unseen] + [result(t, False) for t in dev]
    summary = summarize(rows)
    assert summary["groups"]["dev"]["completion_rate"] == 0.0
    assert not any("dev" in g for g in summary["gate_failures"])  # dev never fails the gate

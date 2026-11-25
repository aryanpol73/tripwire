"""D-071: the two walker gaps found in the first full live gate, replayed with test policies.

1. On sign_up_and_leave the model left a newsletter it never joined, then said it was done.
2. On an unseen layout the model guessed addresses that do not exist and was told "new page".
"""

import re

from evilweb.app import create_app
from evilweb.server import serve_app
from tests.llm_policy import controls
from tripwire.llm.client import PolicySource
from tripwire.llm.walker import LlmWalker
from tripwire.mission import load_mission
from tripwire.walker.base import RunRequest
from unseen.sites import get as get_layout


def run(browser, tmp_path, app, run_id, policy, mission):
    with serve_app(app, run_id) as url:
        walker = LlmWalker(
            RunRequest(
                start_url=url + "/",
                mission=load_mission(mission),
                run_dir=tmp_path / run_id,
                run_id=run_id,
                browser=browser,
                log=lambda _m: None,
            ),
            PolicySource(policy),
        )
        trace = walker.run()
    return trace, walker


def click_named(prompt, pattern, purpose):
    for eid, _role, rest in controls(prompt):
        if re.search(pattern, rest.split(" | ")[0], re.I):
            return "click", {"element_id": eid, "purpose": purpose, "reason": "r"}
    return None


def test_leaving_before_joining_is_refused(browser, tmp_path):
    """The live failure on obstruction-clean-skin2, step by step."""
    calls = {"n": 0}

    def policy(req):
        calls["n"] += 1
        if calls["n"] > 8:
            return "done", {"outcome": "completed", "reason": "r"}
        for pattern, purpose in (
            (r"decline all|reject", "reject_consent"),
            (r"opt out|unsubscribe", "leave"),  # on the newsletter page, try to leave
            (r"^newsletter$", "browse"),
        ):
            action = click_named(req.prompt, pattern, purpose)
            if action and (purpose != "reject_consent" or "(reject control)" in req.prompt):
                return action
        return "done", {"outcome": "completed", "reason": "r"}

    sid = "obstruction-clean-skin2"
    trace, walker = run(browser, tmp_path, create_app(sid), sid, policy, "sign_up_and_leave")
    refused = [h for h in walker.history if "nothing has been joined yet" in h]
    assert refused, "a leave step or done before any sign-up is refused"
    assert not any(p.value == "leave" for p in walker.purpose_of.values())
    assert not any(p.goal.value in ("unsubscribe", "cancel") for p in trace.paths)


def test_a_guessed_address_that_does_not_exist_is_reported_as_not_found(browser, tmp_path):
    """The live failure on streamly-video: guessing /account instead of clicking Profile."""
    queue = [
        ("navigate", {"path": "/account", "purpose": "browse", "reason": "guess"}),
        ("done", {"outcome": "impossible", "reason": "r"}),
    ]

    def policy(_req):
        return queue.pop(0)

    layout = get_layout("streamly-video")
    _trace, walker = run(browser, tmp_path, layout.create_app(), "streamly", policy, "first_visit")
    assert any("page not found (HTTP 404)" in h for h in walker.history)


def test_done_is_allowed_once_something_was_joined(browser, tmp_path):
    """The order check must not get in the way of a correct run."""
    from tests.llm_policy import scripted

    policy = scripted([])  # done(completed) straight away, on a mission with no sign-up
    sid = "consent_asymmetry-clean-skin1"
    _trace, walker = run(browser, tmp_path, create_app(sid), sid, policy, "first_visit")
    assert walker.stats.stopped_by.startswith("done")
    assert not any("joined" in h for h in walker.history)

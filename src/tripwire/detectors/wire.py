"""Wire-level form checks (Phase 9 module 2): what a form sends against what it showed.

For every form the walker submits, compare the request body that left the browser with the
same form as measured on the step just before the submit click. A script can change a form
at the moment it is submitted, after the page was measured; only the request shows that.

- wire.flipped_choice: a checkbox the visitor saw unticked is sent as on.
- wire.injected_optin: a field that was not in the form at all is added at submit with a
  yes-value. Security fields added at submit (CSRF tokens, nonces) are ignored; other added
  fields go to "needs review", because their purpose cannot be measured.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from urllib.parse import parse_qsl, urlsplit

from tripwire.detectors.base import Observation
from tripwire.schemas.trace import Form, Step, Trace


def _path(url: str | None) -> str:
    return urlsplit(url or "").path


def _submissions(trace: Trace) -> Iterator[tuple[Step, Step, Form, list[tuple[str, str]]]]:
    """(step that measured the form, submit step, the form, the body's key/value pairs)."""
    for i, step in enumerate(trace.steps[1:], start=1):
        before = trace.steps[i - 1]
        for r in step.requests:
            if r.method.upper() != "POST" or not r.post_data_redacted:
                continue
            body = r.post_data_redacted
            if body.lstrip().startswith(("{", "[")) or "=" not in body:
                continue  # JSON or unknown bodies do not come from an HTML form
            form = next(
                (
                    f
                    for f in before.forms
                    if f.method.upper() == "POST" and _path(f.action_url) == _path(r.url)
                ),
                None,
            )
            if form is not None:
                yield before, step, form, parse_qsl(body, keep_blank_values=True)


def wire(trace: Trace, config: Mapping) -> Iterator[Observation]:
    on = {v.lower() for v in config["on_values"]}
    security = re.compile(config["security_names"], re.IGNORECASE)
    flipped: list[str] = []
    injected_optin: list[str] = []
    injected_other: list[str] = []
    steps: list[int] = []
    review: list[int] = []
    measured = False
    for before, submit, form, pairs in _submissions(trace):
        measured = True
        fields = {f.name: f for f in form.fields if f.name}
        sent = {}
        for key, value in pairs:
            sent.setdefault(key, value)
        for name, value in sent.items():
            field = fields.get(name)
            if field is None:
                if security.search(name):
                    continue  # a token added at submit is normal, not a choice
                if value.lower() in on:
                    injected_optin.append(f"{name}={value}")
                    steps += [before.index, submit.index]
                else:
                    injected_other.append(name)
                    review.append(submit.index)
                continue
            visible = not field.hidden and not field.off_screen
            if field.type == "checkbox" and visible and not field.prechecked:
                # Unticked when the walker last measured it, and the walker did not tick it.
                flipped.append(f"{name}={value}")
                steps += [before.index, submit.index]
    if not measured:
        return
    yield Observation(
        "wire.flipped_choice",
        bool(flipped),
        sorted(set(steps)) or [trace.steps[-1].index],
        dict(flipped_count=len(flipped), flipped_fields=", ".join(flipped)),
        f"{len(flipped)} unticked checkboxes were sent as ticked when the form was submitted.",
        "Check the page's script did not tick the box in a way the visitor could see.",
    )
    yield Observation(
        "wire.injected_optin",
        bool(injected_optin),
        sorted(set(steps)) or [trace.steps[-1].index],
        dict(
            injected_optin_count=len(injected_optin),
            injected_fields=", ".join(injected_optin),
            unclassified_added_fields=len(injected_other),
        ),
        f"The submitted form carried {len(injected_optin)} opt-ins that were not in the "
        "form shown.",
        "Check whether the added field records a choice the visitor made elsewhere.",
        review_steps=sorted(set(review)),
    )

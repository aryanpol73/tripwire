"""Measure late charges, preselected paid extras, opt-ins and renewal disclosures."""

import re

from tripwire.detectors.base import Observation

_AGREEMENT = re.compile(r"consent|marketing|newsletter|partner|share|offer|promotional", re.I)
_TRIAL = re.compile(r"trial", re.I)


def _selected_offers(candidates, steps):
    if len({line.amount.minor for line in candidates}) <= 1:
        return candidates
    # Use the most recent choice that identifies an advertised offer. Abstain when
    # several advertised prices remain and there is no evidence which one was chosen.
    for step in reversed(steps):
        selected = {
            text.casefold()
            for form in step.forms
            for field in form.fields
            if field.type == "radio" and field.prechecked
            for text in (field.label, field.default_value)
            if text
        }
        matches = [
            line
            for line in candidates
            if any(
                re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", line.label.casefold())
                for name in selected
            )
        ]
        if matches:
            return matches if len({line.amount.minor for line in matches}) == 1 else []
    return []


def sneaking(trace, config):
    seen = set()
    bundled = []
    for step in trace.steps:
        for form in step.forms:
            for f in form.fields:
                key = (form.action_url, f.name)
                if key in seen:
                    continue
                seen.add(key)
                if not _AGREEMENT.search(f"{f.name} {f.label or ''}"):
                    continue
                enabled_value = (f.default_value or "").casefold() in {"1", "yes", "true", "on"}
                if (f.hidden and f.type == "hidden" and enabled_value) or (
                    (f.hidden or f.off_screen) and f.prechecked
                ):
                    bundled.append(step.index)
    yield Observation(
        "sneaking.bundled_optins",
        bool(bundled),
        bundled,
        dict(hidden_optin_count=len(bundled)),
        f"The form carried {len(bundled)} hidden or off-screen opt-ins.",
        "Verify that the submitted fields change an agreement.",
    )
    c = trace.commerce
    if not c:
        return
    addon_steps = []
    prices = []
    for a in c.default_addons:
        if a.preselected:
            addon_steps.append(a.step_index)
            if a.price:
                prices.append((a.price.currency, a.price.minor))
    for item in c.cart:
        excess = item.qty - item.qty_added_by_walker
        if excess > 0:
            addon_steps.append(item.step_index)
            if item.unit_price:
                prices.append((item.unit_price.currency, item.unit_price.minor * excess))
    amount = (
        sum(p for _, p in prices)
        if len(prices) == len(addon_steps) and len({k for k, _ in prices}) <= 1
        else None
    )
    yield Observation(
        "sneaking.preadded_extras",
        bool(addon_steps),
        addon_steps,
        dict(preadded_count=len(addon_steps), preadded_minor=amount),
        f"The cart or plan included {len(addon_steps)} extras the walker did not select.",
        "Compare quantities and paid defaults with the recorded choices.",
    )
    totals = [line for line in c.price_ledger if line.role == "total"]
    if totals:
        final_step = max(max(line.seen_steps or [line.first_step]) for line in totals)
        final_lines = [
            line for line in totals if final_step in (line.seen_steps or [line.first_step])
        ]
        final = max(final_lines, key=lambda line: line.amount.minor)
        earlier = [
            line
            for line in totals
            if line.first_step < final_step and line.amount.currency == final.amount.currency
        ]
        if not earlier:
            earlier = [
                line
                for line in c.price_ledger
                if line.first_step < final_step
                and re.search(r"per (?:seat|month)", line.label, re.I)
                and line.amount.currency == final.amount.currency
            ]
            earlier = _selected_offers(earlier, trace.steps[:final_step])
        if earlier:
            advertised = min(earlier, key=lambda line: line.amount.minor)
            fees = [
                line
                for line in c.price_ledger
                if line.mandatory
                and line.role == "fee"
                and advertised.first_step < line.first_step <= final_step
                and line.amount.currency == final.amount.currency
                and final_step in (line.seen_steps or [line.first_step])
            ]
            drift = sum(line.amount.minor for line in fees)
            final_minor = final.amount.minor
            if "monthly" in final.label.lower():
                final_minor += sum(
                    line.amount.minor for line in fees if "month" not in line.label.lower()
                )
            yield Observation(
                "sneaking.price_drift",
                drift >= config["min_drift_minor"] and final_minor > advertised.amount.minor,
                [advertised.first_step, final_step],
                dict(
                    advertised_total_minor=advertised.amount.minor,
                    final_total_minor=final_minor,
                    drift_from_mandatory_minor=drift,
                    late_mandatory_lines=len(fees),
                    currency=final.amount.currency,
                ),
                f"Previously undisclosed mandatory charges totaled {drift} minor currency units.",
                "Check whether the charges were disclosed earlier or selected explicitly.",
            )
    join = next(
        (p for p in trace.paths if p.goal == "sign_up" and p.completed and p.step_indices), None
    )
    if not join:
        return
    last = join.step_indices[-1]
    if not any(
        _TRIAL.search((s.action.target.accessible_name or "") if s.action.target else "")
        for s in trace.steps[: last + 1]
    ) and not any("trial" in n.text.lower() for n in c.terms):
        return
    terms = [n for n in c.terms if n.step_index < last]
    best = max(
        terms, key=lambda n: (n.mentions_price and n.mentions_date, n.font_size_px), default=None
    )
    missing = not best or not (best.mentions_date and best.mentions_price)
    faint = best and (
        best.font_size_px < config["small_font"]
        or (best.contrast_ratio is not None and best.contrast_ratio < config["low_contrast"])
    )
    yield Observation(
        "sneaking.renewal_disclosure",
        bool(missing or faint),
        [best.step_index if best else max(0, last - 1)],
        dict(
            renewal_date_shown=bool(best and best.mentions_date),
            renewal_font_px=best.font_size_px if best else None,
            renewal_contrast=best.contrast_ratio if best else None,
        ),
        "The observed trial terms lacked a price or date, or fell below the legibility threshold.",
        "Check the pre-confirmation pages for an alternative disclosure.",
    )

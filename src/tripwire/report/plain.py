"""Plain-language wording for the report: what a non-expert should read first.

Every sentence is built only from measured values in the finding. Nothing here judges
intent or legality; the Finding schema's word guard applies to detector text, and the
report tests apply the same guard to this wording.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

FAMILY_NAMES = {
    "consent_asymmetry": "Consent and choice",
    "sneaking": "Sneaking and hidden extras",
    "obstruction": "Obstruction",
    "urgency": "False urgency",
}

RULE_TITLES = {
    "consent.click_asymmetry": "Rejecting takes more effort than accepting",
    "consent.visual_asymmetry": "Accept stands out, reject is hard to see",
    "consent.preselected": "Optional choices already switched on",
    "consent.confirmshaming": "Decline wording",
    "sneaking.price_drift": "Charges that appear late",
    "sneaking.preadded_extras": "Extras added without being chosen",
    "sneaking.renewal_disclosure": "Renewal terms missing or hard to read",
    "sneaking.bundled_optins": "Hidden or off-screen opt-ins",
    "obstruction.roach_motel": "Leaving is harder than joining",
    "obstruction.buried_control": "The way out is hard to find",
    "obstruction.interposed_friction": "Extra steps on the way out",
    "urgency.countdown_reset": "A countdown that restarts",
    "urgency.stock_flux": "A stock count that goes up",
}

METRIC_LABELS = {
    "accept_clicks": "Clicks to accept",
    "reject_clicks": "Clicks to reject",
    "extra_clicks_to_reject": "Extra clicks to reject",
    "reject_on_first_layer": "Reject offered on the first screen",
    "accept_page_loads": "Page loads to accept",
    "reject_page_loads": "Page loads to reject",
    "compared_on_layer": "Banner screen compared",
    "area_ratio": "Accept area \u00f7 reject area",
    "accept_contrast": "Accept text contrast (WCAG)",
    "reject_contrast": "Reject text contrast (WCAG)",
    "accept_font_px": "Accept font size (px)",
    "reject_font_px": "Reject font size (px)",
    "preselected_count": "Optional choices already on",
    "decline_text": "Decline wording",
    "mixed_choice_cues": "Wording mixes accept and reject",
    "advertised_total_minor": "Price shown earlier",
    "final_total_minor": "Final total",
    "drift_from_mandatory_minor": "Late mandatory charges",
    "late_mandatory_lines": "Late mandatory lines",
    "currency": "Currency",
    "preadded_count": "Extras not chosen",
    "preadded_minor": "Value of those extras",
    "renewal_date_shown": "Renewal date shown before confirming",
    "renewal_font_px": "Renewal text size (px)",
    "renewal_contrast": "Renewal text contrast (WCAG)",
    "hidden_optin_count": "Hidden or off-screen opt-ins",
    "unclassified_enabled_hidden_fields": "Enabled hidden fields of unclear purpose",
    "sign_up_clicks": "Clicks to join",
    "leave_clicks": "Clicks to leave",
    "extra_clicks_to_leave": "Extra clicks to leave",
    "exit_channel": "How leaving ends",
    "sign_up_page_loads": "Page loads to join",
    "leave_page_loads": "Page loads to leave",
    "footer_only": "Only in the footer",
    "click_depth": "Clicks before it is visible",
    "font_px": "Font size (px)",
    "contrast": "Text contrast (WCAG)",
    "tree_depth": "Depth in the page structure",
    "unneeded_interstitials": "Steps that asked for nothing needed",
    "seconds_before": "Countdown before the reload (s)",
    "seconds_after": "Countdown after the reload (s)",
    "elapsed_s": "Seconds between the two readings",
    "excess_s": "Extra seconds shown after the reload",
    "timer_restarted": "Countdown restarted",
    "stock_before": "Stock count before the reload",
    "stock_after": "Stock count after the reload",
    "stock_went_up": "Stock count went up",
}

SYMBOLS = {"INR": "\u20b9", "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "JPY": "\u00a5"}


def money(minor: Any, currency: str | None) -> str:
    if not isinstance(minor, int):
        return "unknown"
    code = currency or "INR"
    digits = 0 if code == "JPY" else 2
    value = abs(minor) / (10**digits)
    text = f"{value:,.{digits}f}".removesuffix(".00")
    return f"{'-' if minor < 0 else ''}{SYMBOLS.get(code, code + ' ')}{text}"


def metric_value(key: str, value: Any, metrics: Mapping[str, Any]) -> str:
    if value is None:
        return "not measured"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if key.endswith("_minor"):
        return money(value, metrics.get("currency"))
    if "contrast" in key and isinstance(value, (int, float)):
        return f"{num(float(value))}:1"
    if key == "area_ratio":
        return f"{value:.2f}\u00d7"
    return num(value)


def num(value: Any) -> str:
    """10.0 -> "10", 2.2547 -> "2.25"; anything else unchanged."""
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def clock(seconds: int) -> str:
    """599 -> "09:59", 7199 -> "1:59:59", as a countdown shows it."""
    h, rest = divmod(int(seconds), 3600)
    mins, secs = divmod(rest, 60)
    return f"{h}:{mins:02d}:{secs:02d}" if h else f"{mins:02d}:{secs:02d}"


def _clicks(n: Any) -> str:
    return f"{n} click" + ("" if n == 1 else "s")


def _text_style(font_px: Any, contrast: Any) -> str:
    """ "10px text at 2.25:1 contrast", leaving out whatever was not measurable."""
    parts = []
    if font_px is not None:
        parts.append(f"{num(font_px)}px text")
    if contrast is not None:
        parts.append(f"{num(contrast)}:1 contrast")
    return " at ".join(parts) if parts else "text of unmeasured size and contrast"


def headline(rule: str, m: Mapping[str, Any]) -> str:
    """One sentence a non-expert can repeat after reading it once."""
    cur = m.get("currency")
    if rule == "consent.click_asymmetry":
        text = (
            f"Accepting cookies takes {_clicks(m.get('accept_clicks'))}; "
            f"rejecting takes {_clicks(m.get('reject_clicks'))}."
        )
        if m.get("reject_on_first_layer") is False:
            text += " The first screen of the banner has no reject button."
        return text
    if rule == "consent.visual_asymmetry":
        ratio = num(m.get("area_ratio"))
        text = f"The accept button is {ratio}\u00d7 the size of the reject button"
        if m.get("reject_contrast") is not None and m.get("accept_contrast") is not None:
            text += (
                f"; reject text has {num(m.get('reject_contrast'))}:1 contrast against "
                f"{num(m.get('accept_contrast'))}:1 for accept"
            )
        return text + "."
    if rule == "consent.preselected":
        n = m.get("preselected_count")
        were = "choice was" if n == 1 else "choices were"
        return f"{n} optional consent {were} already switched on."
    if rule == "consent.confirmshaming":
        return f"The decline button reads \u201c{m.get('decline_text')}\u201d."
    if rule == "sneaking.price_drift":
        return (
            f"{money(m.get('drift_from_mandatory_minor'), cur)} in mandatory charges appeared "
            f"only near the end: the price shown earlier was "
            f"{money(m.get('advertised_total_minor'), cur)}, the final total "
            f"{money(m.get('final_total_minor'), cur)}."
        )
    if rule == "sneaking.preadded_extras":
        n = m.get("preadded_count")
        return (
            f"{n} paid extra{'' if n == 1 else 's'} worth "
            f"{money(m.get('preadded_minor'), cur)} {'was' if n == 1 else 'were'} already "
            "in the cart or plan without being chosen."
        )
    if rule == "sneaking.renewal_disclosure":
        if not m.get("renewal_date_shown"):
            return "No renewal date and price were shown before the trial was confirmed."
        style = _text_style(m.get("renewal_font_px"), m.get("renewal_contrast"))
        return f"The renewal terms were shown in {style}."
    if rule == "sneaking.bundled_optins":
        n = m.get("hidden_optin_count")
        return f"The form sent {n} opt-in{'' if n == 1 else 's'} the visitor could not see."
    if rule == "obstruction.roach_motel":
        text = (
            f"Joining took {_clicks(m.get('sign_up_clicks'))}; "
            f"leaving took {_clicks(m.get('leave_clicks'))}"
        )
        channel = m.get("exit_channel")
        if channel and channel != "web":
            text += f", and the last step had to be done by {channel}"
        return text + "."
    if rule == "obstruction.buried_control":
        where = "only in the page footer" if m.get("footer_only") else "small and faint"
        return f"The way out was {where}: {_text_style(m.get('font_px'), m.get('contrast'))}."
    if rule == "obstruction.interposed_friction":
        n = m.get("unneeded_interstitials")
        return f"Leaving passed through {n} extra step{'' if n == 1 else 's'} that asked for nothing needed to leave."  # noqa: E501
    if rule == "urgency.countdown_reset":
        b, a, gap = m.get("seconds_before"), m.get("seconds_after"), m.get("elapsed_s")
        if isinstance(b, int) and isinstance(a, int) and isinstance(gap, (int, float)):
            expected = max(0, round(b - gap))
            return (
                f"The countdown showed {clock(b)}; after a reload {round(gap)} s later it "
                f"showed {clock(a)}, not {clock(expected)}."
            )
    if rule == "urgency.stock_flux":
        return (
            f"The page said only {m.get('stock_before')} left; after a reload, with nothing "
            f"bought, it said {m.get('stock_after')} left."
        )
    return "A measured asymmetry was recorded."

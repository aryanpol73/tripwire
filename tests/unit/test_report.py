"""Phase 5 report: self-contained, plain-worded, never a verdict, honest when empty."""

import base64
import json
import re
import shutil
import struct
import zlib
from pathlib import Path

import pytest

from tripwire.cli import main
from tripwire.detectors.rules import RULES
from tripwire.report import plain
from tripwire.report.builder import build_report, png_size
from tripwire.schemas.finding import _FORBIDDEN_RE

FIXTURES = Path(__file__).parents[1] / "fixtures" / "traces"

SAMPLE_METRICS = {
    "consent.click_asymmetry": dict(accept_clicks=1, reject_clicks=4, reject_on_first_layer=False),
    "consent.visual_asymmetry": dict(area_ratio=9.333, accept_contrast=6.82, reject_contrast=2.3),
    "consent.preselected": dict(preselected_count=3),
    "consent.confirmshaming": dict(decline_text="No thanks, I like paying more"),
    "sneaking.price_drift": dict(
        advertised_total_minor=23900,
        final_total_minor=51500,
        drift_from_mandatory_minor=12800,
        currency="INR",
    ),
    "sneaking.preadded_extras": dict(preadded_count=1, preadded_minor=900, currency="INR"),
    "sneaking.renewal_disclosure": dict(renewal_date_shown=True, renewal_font_px=9.0),
    "sneaking.bundled_optins": dict(hidden_optin_count=2),
    "obstruction.roach_motel": dict(sign_up_clicks=3, leave_clicks=7, exit_channel="phone"),
    "obstruction.buried_control": dict(footer_only=True, font_px=10.0, contrast=2.254),
    "obstruction.interposed_friction": dict(unneeded_interstitials=1),
    "urgency.countdown_reset": dict(seconds_before=597, seconds_after=599, elapsed_s=4.0),
    "urgency.stock_flux": dict(stock_before=2, stock_after=4),
    "wire.flipped_choice": dict(flipped_count=1, flipped_fields="partner_deals=1"),
    "wire.injected_optin": dict(injected_fields="partner_data_sharing=1"),
    "nagging.repeat_popup": dict(reappearances=2, popup_purpose="newsletter"),
    "nagging.forced_registration": dict(reached_by="City"),
}


def visible_text(html: str) -> str:
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    html = re.sub(r'(src|href)="data:[^"]*"', "", html)
    return re.sub(r"<[^>]+>", " ", html)


def run_dir(tmp_path: Path, fixture: str) -> Path:
    d = tmp_path / fixture
    d.mkdir()
    shutil.copy(FIXTURES / f"{fixture}.json", d / "trace.json")
    return d


@pytest.mark.parametrize("rule", sorted(RULES))
def test_every_rule_has_a_plain_one_sentence_headline_without_verdicts(rule):
    text = plain.headline(rule, SAMPLE_METRICS[rule])
    assert rule in plain.RULE_TITLES
    assert "None" not in text and len(text) <= 300 and "\n" not in text
    assert not _FORBIDDEN_RE.search(text + plain.RULE_TITLES[rule])


def test_headline_reads_like_a_sentence():
    assert plain.headline("sneaking.price_drift", SAMPLE_METRICS["sneaking.price_drift"]) == (
        "₹128 in mandatory charges appeared only near the end: the price shown earlier "
        "was ₹239, the final total ₹515."
    )
    assert plain.headline("obstruction.interposed_friction", {"unneeded_interstitials": 1}) == (
        "Leaving passed through 1 extra step that asked for nothing needed to leave."
    )


@pytest.mark.parametrize(
    ("minor", "currency", "text"),
    [(12800, "INR", "₹128"), (1999, "USD", "$19.99"), (123456, "EUR", "€1,234.56")],
)
def test_money(minor, currency, text):
    assert plain.money(minor, currency) == text


def test_metric_values_are_human_readable():
    m = {"currency": "INR"}
    assert plain.metric_value("final_total_minor", 51500, m) == "₹515"
    assert plain.metric_value("contrast", 2.2547, m) == "2.25:1"
    assert plain.metric_value("footer_only", True, m) == "yes"
    assert plain.metric_value("font_px", 10.0, m) == "10"
    assert plain.metric_value("renewal_font_px", None, m) == "not measured"


def test_png_size_reads_the_header(tmp_path):
    ihdr = struct.pack(">IIBBBBB", 1280, 2400, 8, 2, 0, 0, 0)
    chunk = b"IHDR" + ihdr
    crc = struct.pack(">I", zlib.crc32(chunk))
    png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + chunk + crc
    (tmp_path / "a.png").write_bytes(png)
    (tmp_path / "b.png").write_bytes(b"not a png at all, longer than 24 bytes")
    assert png_size(tmp_path / "a.png") == (1280, 2400)
    assert png_size(tmp_path / "b.png") is None


@pytest.mark.parametrize("fixture", ["consent_asymmetry_violating", "sneaking_violating"])
def test_report_is_self_contained_and_carries_the_disclaimer(tmp_path, fixture):
    html = build_report(run_dir(tmp_path, fixture)).read_text(encoding="utf-8")
    assert "<script" not in html and "<link" not in html
    assert not re.search(r'(src|href)="(https?:)?//', html)
    assert "evidence, not a legal verdict" in html
    assert "Measured findings" in html
    assert not _FORBIDDEN_RE.search(visible_text(html).replace("not a legal verdict", ""))


def test_findings_download_round_trips(tmp_path):
    d = run_dir(tmp_path, "consent_asymmetry_violating")
    html = build_report(d).read_text(encoding="utf-8")
    encoded = re.search(r'href="data:application/json;base64,([^"]+)"', html)[1]
    data = json.loads(base64.b64decode(encoded))
    assert data["findings"] and {f["detector"] for f in data["findings"]} <= set(RULES)


@pytest.mark.parametrize("fixture", ["consent_asymmetry_clean", "obstruction_clean"])
def test_no_findings_states_coverage_and_never_says_clean(tmp_path, fixture):
    html = build_report(run_dir(tmp_path, fixture)).read_text(encoding="utf-8")
    block = re.search(r'<div class="panel empty">(.*?)</div>', html, re.S)[1]
    assert "No pattern crossed a threshold" in block
    assert "steps of the" in block and "not measured" in block
    assert not re.search(r"\b(clean|safe|compliant|no dark patterns)\b", block, re.I)
    assert "Measured findings" not in html


def test_missing_screenshot_is_reported_not_hidden(tmp_path):
    html = build_report(run_dir(tmp_path, "obstruction_violating")).read_text(encoding="utf-8")
    assert "is missing from the run folder" in html


def test_cli_report_writes_the_file(tmp_path, capsys):
    d = run_dir(tmp_path, "sneaking_violating")
    assert main(["report", str(d)]) == 0
    assert (d / "report.html").is_file()
    assert main(["report", str(tmp_path / "nowhere")]) == 2

"""Phase 5 against a real run: full-page screenshots, and boxes on the controls that matter."""

import re

from evilweb import scenarios
from evilweb.server import serve
from tripwire.detectors.base import finding_set, measurements
from tripwire.mission import load_mission
from tripwire.report.builder import build_report, png_size
from tripwire.schemas.io import write_model
from tripwire.walker.scripted_walker import RunRequest, ScriptedWalker

SCENARIO = "obstruction-blatant-skin3"


def test_report_boxes_the_buried_way_out_on_a_full_page_screenshot(browser, tmp_path):
    sc = scenarios.get(SCENARIO)
    run_dir = tmp_path / "run"
    with serve(SCENARIO) as url:
        trace = ScriptedWalker(
            RunRequest(
                start_url=url + "/",
                mission=load_mission(sc.mission),
                run_dir=run_dir,
                run_id=SCENARIO,
                site_type=sc.site_type,
                scenario_id=SCENARIO,
                browser=browser,
            )
        ).run()
    write_model(trace, run_dir / "trace.json")
    write_model(finding_set(trace, measurements(trace)), run_dir / "findings.json")

    buried = next(s for s in trace.steps if s.index == 8)
    _width, height = png_size(run_dir / buried.screenshot)
    footer = [e for e in buried.ui.elements if e.landmark == "contentinfo"]
    assert footer and all(e.bbox.y + e.bbox.height <= height for e in footer)  # full page

    html = build_report(run_dir).read_text(encoding="utf-8")
    card = html[html.index("The way out is hard to find") :]
    card = card[: card.index("</article>")]
    box = re.search(r'class="box focus" style="left:([\d.]+)%;top:([\d.]+)%[^"]*"><b>Way out', card)
    assert box, "the buried leave control is boxed"
    left, top = float(box[1]), float(box[2])
    assert 0 <= left < 100 and 50 < top < 100  # in the lower half: the footer
    assert "data:image/png;base64," in card
    assert "Joining compared with leaving" in html

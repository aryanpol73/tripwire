"""Re-render a saved Trace as text, without a browser. Phase 5 adds the HTML report."""

from __future__ import annotations

from urllib.parse import urlsplit

from tripwire.schemas.trace import Trace


def _money(minor: int, currency: str) -> str:
    return f"{currency} {minor / 100:,.2f}"


def render(trace: Trace) -> str:
    out = [
        f"Run {trace.run_id}  ({trace.mode}, mission {trace.mission}, site {trace.site_type})",
        f"Site {trace.site_url}  scenario {trace.scenario_id or '-'}  status {trace.status}",
        (
            f"Used {trace.budgets_used.steps}/{trace.budget_limits.steps} steps, "
            f"{trace.budgets_used.page_loads}/{trace.budget_limits.page_loads} page loads, "
            f"{trace.budgets_used.wall_seconds:.1f}/{trace.budget_limits.wall_seconds:.0f} s"
        ),
        "",
        "Steps",
    ]
    for s in trace.steps:
        target = s.action.target
        what = (target.accessible_name or target.visible_text) if target else s.action.value
        load = "load" if s.page_load else "    "
        overlays = ", ".join(f"{o.purpose} {o.kind} L{o.layer}" for o in s.overlays)
        out.append(
            f"  {s.index:>3}  {s.action.kind:<14} {load}  {urlsplit(s.url_after).path:<28} "
            f"{(what or '')[:40]:<40} {overlays}"
        )
    out += ["", "Paths"]
    for p in trace.paths:
        how = "measured from the page" if not p.executed else "walked"
        end = "" if p.completed else "  (not completed)"
        channel = "" if p.exit_channel == "web" else f"  ends: {p.exit_channel} only"
        out.append(
            f"  {p.name:<16} {p.clicks} clicks, {p.page_loads} page loads, {how}{end}{channel}"
        )
    if trace.intents:
        out += ["", "Intents"]
        out += [f"  {i.goal:<16} {'succeeded' if i.success else 'failed'}" for i in trace.intents]
    if trace.commerce:
        c = trace.commerce
        out += ["", "Price ledger (label, amount, role, mandatory, first step)"]
        out += [
            f"  {line.label[:40]:<40} {_money(line.amount.minor, line.amount.currency):>14} "
            f"{line.role:<9} {'yes' if line.mandatory else 'no ':<3}  {line.first_step}"
            for line in c.price_ledger
        ]
        if c.cart:
            out += ["", "Cart (qty / chosen by walker)"]
            out += [f"  {i.name:<30} {i.qty} / {i.qty_added_by_walker}" for i in c.cart]
        if c.default_addons:
            out += ["", "Paid add-ons (pre-selected?)"]
            out += [
                f"  {a.label[:50]:<50} {'yes' if a.preselected else 'no'}" for a in c.default_addons
            ]
        if c.terms:
            out += ["", "Terms shown (font px, contrast)"]
            out += [f"  {t.font_size_px:>4} px  {t.contrast_ratio}  {t.text[:70]}" for t in c.terms]
    if trace.notes:
        out += ["", "Notes"]
        out += [f"  [{n.kind}] step {n.step_index}: {n.message}" for n in trace.notes]
    return "\n".join(out)

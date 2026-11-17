"""The catalog of v1 rule ids. Detectors (Phase 4) implement these; ground truth refers to them.

Keeping the ids in one place means a typo in a ground-truth file or a detector is caught
by validation instead of silently scoring zero.
"""

from __future__ import annotations

from dataclasses import dataclass

from tripwire.schemas.finding import Family, Tier


@dataclass(frozen=True)
class Rule:
    id: str
    family: Family
    tier: Tier
    question: str  # what the rule measures, in plain words


RULES: dict[str, Rule] = {
    r.id: r
    for r in (
        Rule(
            "consent.click_asymmetry",
            Family.CONSENT_ASYMMETRY,
            Tier.A,
            "Does rejecting take more clicks than accepting, or is reject missing from layer 1?",
        ),
        Rule(
            "consent.visual_asymmetry",
            Family.CONSENT_ASYMMETRY,
            Tier.A,
            "Is the accept control much larger or more legible than the reject control?",
        ),
        Rule(
            "consent.preselected",
            Family.CONSENT_ASYMMETRY,
            Tier.A,
            "Are non-essential consent toggles or marketing boxes checked by default?",
        ),
        Rule(
            "consent.confirmshaming",
            Family.CONSENT_ASYMMETRY,
            Tier.B,
            "Does the decline wording shame the user or use a double negative?",
        ),
        Rule(
            "sneaking.price_drift",
            Family.SNEAKING,
            Tier.A,
            "Do mandatory charges appear only after a lower total was shown?",
        ),
        Rule(
            "sneaking.preadded_extras",
            Family.SNEAKING,
            Tier.A,
            "Is anything in the cart or plan that the walker did not add, or pre-checked?",
        ),
        Rule(
            "sneaking.renewal_disclosure",
            Family.SNEAKING,
            Tier.A,
            "Is the renewal price or date missing, tiny or low-contrast before confirming?",
        ),
        Rule(
            "sneaking.bundled_optins",
            Family.SNEAKING,
            Tier.A,
            "Does a form carry hidden or off-screen opt-ins the user cannot see?",
        ),
        Rule(
            "obstruction.roach_motel",
            Family.OBSTRUCTION,
            Tier.A,
            "Does leaving take 3+ more clicks than joining, or only work offline?",
        ),
        Rule(
            "obstruction.buried_control",
            Family.OBSTRUCTION,
            Tier.A,
            "Is the leave control only in the footer, deep in the tree, or small and faint?",
        ),
        Rule(
            "obstruction.interposed_friction",
            Family.OBSTRUCTION,
            Tier.A,
            "Does the leave path include interstitials that ask for no required input?",
        ),
    )
}

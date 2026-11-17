"""Building blocks shared by the Trace and Finding schemas."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    Strict,
    StringConstraints,
)


class Model(BaseModel):
    """Base for every schema model.

    extra="forbid" turns a typo'd field name into an error instead of silently dropping it.
    That matters because a Trace is written by one program (the walker) and read by another
    (the detectors), often weeks apart.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]

# Strict: pydantic's default "lax" mode would accept 1499.0 and quietly turn it into 1499.
# Money must never pass through a float, so a float here is a bug we want to see.
MinorUnits = Annotated[int, Strict()]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]

# A share of something, e.g. how much of the viewport an overlay covers.
Fraction = Annotated[float, Field(ge=0.0, le=1.0)]

# WCAG contrast ratios run from 1:1 (same colour) to 21:1 (black on white).
ContrastRatio = Annotated[float, Field(ge=1.0, le=21.0)]


class Money(Model):
    """An amount in integer minor units (paise, cents) plus an ISO 4217 currency code.

    Signed: a discount is negative, a fee is positive.
    """

    minor: MinorUnits
    currency: CurrencyCode


def _relative_artifact_path(value: str) -> str:
    # Artifact paths are relative to the run folder so a run can be zipped, moved or
    # committed as a fixture without breaking its references.
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or ":" in value:
        raise ValueError(f"artifact path must be relative to the run folder: {value!r}")
    return path.as_posix()


ArtifactPath = Annotated[str, AfterValidator(_relative_artifact_path)]


def _http_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(f"expected an absolute http(s) URL: {value!r}")
    return value


HttpUrl = Annotated[str, AfterValidator(_http_url)]


class BoundingBox(Model):
    """Position and size in CSS pixels, relative to the top-left of the page."""

    x: float
    y: float
    width: NonNegativeFloat
    height: NonNegativeFloat

    @property
    def area(self) -> float:
        return self.width * self.height

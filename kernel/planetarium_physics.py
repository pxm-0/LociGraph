from __future__ import annotations

import math

MASS_FORMULA_VERSION = "v1"
MASS_WEIGHT_REVISION = 0.25
MASS_WEIGHT_EDGE = 0.25
MASS_WEIGHT_CONTRADICTION = 0.25
MASS_WEIGHT_PIN = 0.25

NEUTRAL_NORMALIZED_VALUE = 0.5

BLACK_HOLE_MASS_PERCENTILE = 0.9
MIN_CONCEPTS_FOR_BLACK_HOLE = 5

BRIGHTNESS_DECAY_HALFLIFE_DAYS = 30.0

NODE_MIN_RADIUS = 1.0
NODE_MAX_RADIUS = 5.0

COLOR_BY_VISUAL_CLASS = {
    "planet": "#4a90d9",
    "black_hole": "#1a1a2e",
}


def normalize(values: dict[str, float]) -> dict[str, float]:
    """Min-max normalize a concept_id -> raw value mapping to [0, 1]. If every
    value is equal (including a single concept), every normalized value is
    NEUTRAL_NORMALIZED_VALUE rather than dividing by zero."""
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi == lo:
        return dict.fromkeys(values, NEUTRAL_NORMALIZED_VALUE)
    return {key: (value - lo) / (hi - lo) for key, value in values.items()}


def mass_percentiles(masses: dict[str, float]) -> dict[str, float]:
    """Percentile rank (0-1) of each concept's mass among all given masses —
    the fraction of other masses strictly below it, so tied masses get the
    same percentile. A single concept is trivially the top (1.0)."""
    if not masses:
        return {}
    values = list(masses.values())
    n = len(values)
    if n == 1:
        return dict.fromkeys(masses, 1.0)
    return {
        key: sum(1 for v in values if v < value) / (n - 1) for key, value in masses.items()
    }


def compute_mass(
    *,
    normalized_revision: float,
    normalized_edge: float,
    normalized_contradiction: float,
    normalized_pin: float,
) -> float:
    return (
        MASS_WEIGHT_REVISION * normalized_revision
        + MASS_WEIGHT_EDGE * normalized_edge
        + MASS_WEIGHT_CONTRADICTION * normalized_contradiction
        + MASS_WEIGHT_PIN * normalized_pin
    )


def classify_visual_class(*, mass: float, mass_percentile: float, concept_count: int) -> str:
    """`mass_percentile` is this concept's percentile rank among all of the
    user's concepts' masses (from `mass_percentiles`) — computed once across
    the full set, then passed in per-concept here."""
    if (
        concept_count >= MIN_CONCEPTS_FOR_BLACK_HOLE
        and mass_percentile >= BLACK_HOLE_MASS_PERCENTILE
    ):
        return "black_hole"
    return "planet"


def compute_brightness(days_since_activity: float) -> float:
    return math.exp(-days_since_activity / BRIGHTNESS_DECAY_HALFLIFE_DAYS)


def node_radius(normalized_mass: float) -> float:
    return NODE_MIN_RADIUS + normalized_mass * (NODE_MAX_RADIUS - NODE_MIN_RADIUS)


def color_for_visual_class(visual_class: str) -> str:
    return COLOR_BY_VISUAL_CLASS[visual_class]


def spherical_from_cartesian(x: float, y: float, z: float) -> tuple[float, float]:
    """Returns (theta, phi): polar angle from +z and azimuthal angle in the
    xy-plane, both measured from the origin."""
    r = math.sqrt(x**2 + y**2 + z**2)
    theta = math.acos(z / r) if r > 0 else 0.0
    phi = math.atan2(y, x)
    return theta, phi

from __future__ import annotations

import math

from kernel.planetarium_physics import (
    BLACK_HOLE_MASS_PERCENTILE,
    BRIGHTNESS_DECAY_HALFLIFE_DAYS,
    MIN_CONCEPTS_FOR_BLACK_HOLE,
    NEUTRAL_NORMALIZED_VALUE,
    NODE_MAX_RADIUS,
    NODE_MIN_RADIUS,
    classify_visual_class,
    color_for_visual_class,
    compute_brightness,
    compute_mass,
    mass_percentiles,
    node_radius,
    normalize,
    spherical_from_cartesian,
)


def test_normalize_scales_to_zero_one_range():
    result = normalize({"a": 0.0, "b": 5.0, "c": 10.0})
    assert result == {"a": 0.0, "b": 0.5, "c": 1.0}


def test_normalize_returns_neutral_value_when_all_tied():
    result = normalize({"a": 3.0, "b": 3.0})
    assert result == {"a": NEUTRAL_NORMALIZED_VALUE, "b": NEUTRAL_NORMALIZED_VALUE}


def test_normalize_empty_returns_empty():
    assert normalize({}) == {}


def test_mass_percentiles_ranks_ties_identically():
    result = mass_percentiles({"a": 1.0, "b": 1.0, "c": 2.0})
    assert result["a"] == result["b"]
    assert result["c"] > result["a"]


def test_mass_percentiles_single_concept_is_top():
    assert mass_percentiles({"a": 5.0}) == {"a": 1.0}


def test_compute_mass_is_equal_weighted_average():
    mass = compute_mass(
        normalized_revision=1.0,
        normalized_edge=0.0,
        normalized_contradiction=0.0,
        normalized_pin=0.0,
    )
    assert mass == 0.25


def test_classify_visual_class_black_hole_above_threshold():
    visual_class = classify_visual_class(
        mass=0.9,
        mass_percentile=BLACK_HOLE_MASS_PERCENTILE,
        concept_count=MIN_CONCEPTS_FOR_BLACK_HOLE,
    )
    assert visual_class == "black_hole"


def test_classify_visual_class_planet_below_threshold():
    visual_class = classify_visual_class(
        mass=0.9, mass_percentile=0.5, concept_count=MIN_CONCEPTS_FOR_BLACK_HOLE
    )
    assert visual_class == "planet"


def test_classify_visual_class_too_few_concepts_is_always_planet():
    visual_class = classify_visual_class(
        mass=0.99, mass_percentile=1.0, concept_count=MIN_CONCEPTS_FOR_BLACK_HOLE - 1
    )
    assert visual_class == "planet"


def test_compute_brightness_decays_over_time():
    fresh = compute_brightness(0.0)
    old = compute_brightness(BRIGHTNESS_DECAY_HALFLIFE_DAYS)
    assert fresh == 1.0
    assert math.isclose(old, math.exp(-1), rel_tol=1e-9)
    assert old < fresh


def test_node_radius_scales_between_min_and_max():
    assert node_radius(0.0) == NODE_MIN_RADIUS
    assert node_radius(1.0) == NODE_MAX_RADIUS


def test_color_for_visual_class_known_values():
    assert color_for_visual_class("planet") == "#4a90d9"
    assert color_for_visual_class("black_hole") == "#1a1a2e"


def test_spherical_from_cartesian_origin_is_zero_theta():
    theta, phi = spherical_from_cartesian(0.0, 0.0, 0.0)
    assert theta == 0.0
    assert phi == 0.0


def test_spherical_from_cartesian_on_axis():
    theta, phi = spherical_from_cartesian(0.0, 0.0, 1.0)
    assert math.isclose(theta, 0.0, abs_tol=1e-9)

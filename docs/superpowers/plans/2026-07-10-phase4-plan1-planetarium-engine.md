# Planetarium Engine (Phase 4 Plan 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute and persist a per-user "planetarium projection" — one `planetary_nodes` row per concept with a 3D position, mass, brightness, and visual classification — as a rebuildable derived cache, with no new API endpoints or frontend (those are Plans 2 and 3).

**Architecture:** A new `planetary_nodes` table + `PlanetaryNodeRepository`. Two pure, DB-free computation modules (`kernel/planetarium_physics.py` for the mass/brightness/visual-class formulas, `kernel/planetarium_projection.py` for the UMAP spatial projection). One orchestration function, `kernel.planetarium.rebuild_planetarium(conn, user_id)`, that gathers signals from existing tables, calls the two pure modules, and replaces the user's `planetary_nodes` rows in one transaction. A dramatiq actor (`worker/tasks/project_planetarium.py`) wraps it using the exact `Job`/`JobRepository` pattern every other worker task already uses, including the `on_retry_exhausted` healing wrapper.

**Tech Stack:** Python 3.12, SQLAlchemy `text()` (no ORM), asyncpg, Postgres 16 + pgvector, dramatiq, numpy, `umap-learn` (new dependency).

## Global Constraints

- Migration `0013`, `down_revision = "0012"` (current head).
- Every new table gets `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` + a `<table>_user_isolation` policy on `user_id = current_setting('app.current_user_id')::uuid` — exact pattern used by every prior migration (see `migrations/versions/0012_custodian_logging.py`).
- Only 4 real signals feed mass — no others: `revision_count`, `edge_count` (from `claim_concept_edges`), `contradiction_count`, `pin_count` (from `importance_signals`). Do not invent data for the 6 unbuilt factors (frequency, emotional_intensity, time_depth, ai_significance, custodian_interaction, recency-as-a-separate-factor) named in `implementation/02_Data_Model.md` — that schema was never built.
- `MASS_FORMULA_VERSION = "v1"`, equal weights `MASS_WEIGHT_REVISION = MASS_WEIGHT_EDGE = MASS_WEIGHT_CONTRADICTION = MASS_WEIGHT_PIN = 0.25`.
- Min-max normalization per signal across a user's concepts; `NEUTRAL_NORMALIZED_VALUE = 0.5` when every value is tied (avoids divide-by-zero).
- `visual_class` values shipped in this plan: `"planet"` (default) and `"black_hole"` (top decile by mass, `BLACK_HOLE_MASS_PERCENTILE = 0.9`, only when the user has at least `MIN_CONCEPTS_FOR_BLACK_HOLE = 5` concepts). `moon`, `star`, `constellation_anchor`, `archive_point` are NOT produced by this plan — no data source exists yet.
- `BRIGHTNESS_DECAY_HALFLIFE_DAYS = 30.0` — `brightness = exp(-days_since_activity / 30.0)`.
- `NODE_MIN_RADIUS = 1.0`, `NODE_MAX_RADIUS = 5.0`.
- `COLOR_BY_VISUAL_CLASS = {"planet": "#4a90d9", "black_hole": "#1a1a2e"}`.
- UMAP: `n_components=3`, `UMAP_RANDOM_STATE = 42`, `UMAP_N_NEIGHBORS_DEFAULT = 15` (capped to `min(15, n_concepts - 1)`). Below `MIN_CONCEPTS_FOR_UMAP = 3` embeddable concepts, skip UMAP — place each at `(index * UMAP_FALLBACK_JITTER, 0.0, 0.0)`, `UMAP_FALLBACK_JITTER = 0.1`. A concept with zero linked claim embeddings is placed at the origin `(0.0, 0.0, 0.0)` regardless of total concept count.
- `PROJECTION_ALGORITHM = "umap"`, `PROJECTION_VERSION = "v1"`; stored `projection_version` column value is `f"{MASS_FORMULA_VERSION}/{PROJECTION_VERSION}"` (one string capturing both formula and projection versions, since either changing invalidates the cache).
- A rebuild is delete-all-then-insert for that user in one transaction (`UNIQUE (user_id, concept_id)` on the table). Never partial/incremental.
- `job_type = "project_planetarium"` — free-text column, no registry to update. Actor follows `worker/tasks/embed_claims.py`'s exact shape: `queue_name="extraction"`, `max_retries=3`, `on_retry_exhausted="heal_project_planetarium"`, `mark_running`/`record_attempt`/`mark_completed` via `JobRepository`.
- No API endpoints, no frontend, no scheduled/automatic triggering — all deferred to Plans 2, 3, and 4 respectively.

---

### Task 1: Migration, model, and repository

**Files:**
- Create: `migrations/versions/0013_planetary_nodes.py`
- Modify: `kernel/models.py` (add `PlanetaryNode` dataclass)
- Create: `kernel/db/planetary_nodes.py`
- Modify: `tests/conftest.py` (add `planetary_nodes` cleanup to `make_user`'s teardown)
- Test: `tests/kernel/test_planetary_nodes_repository.py`

**Interfaces:**
- Produces: `PlanetaryNode` dataclass (`kernel/models.py`) with fields `id, user_id, concept_id, x, y, z, theta, phi, radius, mass, brightness, color, visual_class, projection_version, projection_algorithm, created_at` and a `from_row(cls, row)` classmethod, matching every other model in the file.
- Produces: `PlanetaryNodeRepository(conn)` (`kernel/db/planetary_nodes.py`) with `async def replace_all_for_user(self, user_id: str | UUID, nodes: list[dict[str, Any]]) -> list[PlanetaryNode]` and `async def list_for_user(self, user_id: str | UUID) -> list[PlanetaryNode]`. Each dict in `nodes` must have exactly the keys: `concept_id, x, y, z, theta, phi, radius, mass, brightness, color, visual_class, projection_version, projection_algorithm` (no `user_id` — the method adds it).

- [ ] **Step 1: Write the migration**

Create `migrations/versions/0013_planetary_nodes.py`:

```python
"""planetary_nodes — Planetarium projection cache

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-10
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

DATA_TABLES = ["planetary_nodes"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE planetary_nodes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            concept_id UUID NOT NULL REFERENCES concepts(id),
            x DOUBLE PRECISION NOT NULL,
            y DOUBLE PRECISION NOT NULL,
            z DOUBLE PRECISION NOT NULL,
            theta DOUBLE PRECISION NOT NULL,
            phi DOUBLE PRECISION NOT NULL,
            radius DOUBLE PRECISION NOT NULL,
            mass DOUBLE PRECISION NOT NULL,
            brightness DOUBLE PRECISION NOT NULL,
            color TEXT NOT NULL,
            visual_class TEXT NOT NULL,
            projection_version TEXT NOT NULL,
            projection_algorithm TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, concept_id)
        )
        """
    )
    for table in DATA_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO locigraph_app")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_user_isolation ON {table} "
            "USING (user_id = current_setting('app.current_user_id')::uuid) "
            "WITH CHECK (user_id = current_setting('app.current_user_id')::uuid)"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS planetary_nodes CASCADE")
```

- [ ] **Step 2: Apply the migration**

Run: `alembic upgrade head`
Expected: output ends with `... -> 0013, planetary_nodes — Planetarium projection cache`

- [ ] **Step 3: Add `planetary_nodes` cleanup to the test teardown**

In `tests/conftest.py`, in the `make_user` fixture's teardown loop, add a `DELETE FROM planetary_nodes` line **before** `DELETE FROM concepts` (it has a `concept_id` foreign key, so it must go first):

```python
            await conn.execute(text("DELETE FROM custodian_logged_items"))
            await conn.execute(text("DELETE FROM notes"))
            await conn.execute(text("DELETE FROM importance_signals"))
            await conn.execute(text("DELETE FROM custodian_messages"))
            await conn.execute(text("DELETE FROM custodian_sessions"))
            await conn.execute(text("DELETE FROM claim_concept_edges"))
            await conn.execute(text("DELETE FROM revisions"))
            await conn.execute(text("DELETE FROM contradictions"))
            await conn.execute(text("DELETE FROM planetary_nodes"))
            await conn.execute(text("DELETE FROM concepts"))
```

- [ ] **Step 4: Write the failing test**

Create `tests/kernel/test_planetary_nodes_repository.py`:

```python
from __future__ import annotations

import pytest

from kernel.db.concepts import ConceptRepository
from kernel.db.planetary_nodes import PlanetaryNodeRepository
from kernel.db.session import session


def _node(concept_id, *, visual_class="planet", mass=0.5) -> dict:
    return {
        "concept_id": concept_id,
        "x": 1.0,
        "y": 2.0,
        "z": 3.0,
        "theta": 0.1,
        "phi": 0.2,
        "radius": 2.0,
        "mass": mass,
        "brightness": 0.9,
        "color": "#4a90d9",
        "visual_class": visual_class,
        "projection_version": "v1/v1",
        "projection_algorithm": "umap",
    }


@pytest.mark.asyncio
async def test_replace_all_for_user_inserts_and_replaces(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="Alpha", concept_type="entity"
        )
        assert concept is not None
        repo = PlanetaryNodeRepository(conn)

        first = await repo.replace_all_for_user(user_id, [_node(concept.id)])
        assert len(first) == 1
        assert first[0].concept_id == concept.id
        assert first[0].visual_class == "planet"

        second = await repo.replace_all_for_user(
            user_id, [_node(concept.id, visual_class="black_hole", mass=0.99)]
        )
        listed = await repo.list_for_user(user_id)

    assert len(second) == 1
    assert len(listed) == 1
    assert listed[0].visual_class == "black_hole"
    assert listed[0].mass == 0.99


@pytest.mark.asyncio
async def test_replace_all_for_user_can_clear_to_empty(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        concept = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="Beta", concept_type="entity"
        )
        assert concept is not None
        repo = PlanetaryNodeRepository(conn)
        await repo.replace_all_for_user(user_id, [_node(concept.id)])

        cleared = await repo.replace_all_for_user(user_id, [])
        listed = await repo.list_for_user(user_id)

    assert cleared == []
    assert listed == []
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `pytest tests/kernel/test_planetary_nodes_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kernel.db.planetary_nodes'`

- [ ] **Step 6: Add the `PlanetaryNode` model**

In `kernel/models.py`, after the `ImportanceSignal` dataclass at the end of the file, add:

```python
@dataclass(frozen=True, slots=True)
class PlanetaryNode:
    id: UUID
    user_id: UUID
    concept_id: UUID
    x: float
    y: float
    z: float
    theta: float
    phi: float
    radius: float
    mass: float
    brightness: float
    color: str
    visual_class: str
    projection_version: str
    projection_algorithm: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> PlanetaryNode:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            concept_id=row["concept_id"],
            x=float(row["x"]),
            y=float(row["y"]),
            z=float(row["z"]),
            theta=float(row["theta"]),
            phi=float(row["phi"]),
            radius=float(row["radius"]),
            mass=float(row["mass"]),
            brightness=float(row["brightness"]),
            color=row["color"],
            visual_class=row["visual_class"],
            projection_version=row["projection_version"],
            projection_algorithm=row["projection_algorithm"],
            created_at=row["created_at"],
        )
```

- [ ] **Step 7: Implement `PlanetaryNodeRepository`**

Create `kernel/db/planetary_nodes.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from kernel.db.base_repository import BaseRepository
from kernel.models import PlanetaryNode

_COLUMNS = (
    "id, user_id, concept_id, x, y, z, theta, phi, radius, mass, brightness, "
    "color, visual_class, projection_version, projection_algorithm, created_at"
)


def _as_mapping(row: RowMapping) -> Mapping[str, Any]:
    return row  # type: ignore[return-value]


class PlanetaryNodeRepository(BaseRepository):
    async def replace_all_for_user(
        self, user_id: str | UUID, nodes: list[dict[str, Any]]
    ) -> list[PlanetaryNode]:
        """Delete every existing node for `user_id` and insert `nodes` in its
        place, in one transaction — a rebuild always fully replaces the
        projection, it never patches it incrementally."""
        await self.conn.execute(
            text("DELETE FROM planetary_nodes WHERE user_id = :user_id"),
            {"user_id": str(user_id)},
        )
        created: list[PlanetaryNode] = []
        for node in nodes:
            row = (
                await self.conn.execute(
                    text(
                        f"""
                        INSERT INTO planetary_nodes
                            (user_id, concept_id, x, y, z, theta, phi, radius, mass,
                             brightness, color, visual_class, projection_version,
                             projection_algorithm)
                        VALUES
                            (:user_id, :concept_id, :x, :y, :z, :theta, :phi, :radius,
                             :mass, :brightness, :color, :visual_class,
                             :projection_version, :projection_algorithm)
                        RETURNING {_COLUMNS}
                        """
                    ),
                    {"user_id": str(user_id), **node, "concept_id": str(node["concept_id"])},
                )
            ).mappings().one()
            created.append(PlanetaryNode.from_row(_as_mapping(row)))
        return created

    async def list_for_user(self, user_id: str | UUID) -> list[PlanetaryNode]:
        rows = (
            await self.conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM planetary_nodes "
                    "WHERE user_id = :user_id ORDER BY created_at DESC"
                ),
                {"user_id": str(user_id)},
            )
        ).mappings().all()
        return [PlanetaryNode.from_row(_as_mapping(r)) for r in rows]
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `pytest tests/kernel/test_planetary_nodes_repository.py -v`
Expected: `2 passed`

- [ ] **Step 9: Commit**

```bash
git add migrations/versions/0013_planetary_nodes.py kernel/models.py kernel/db/planetary_nodes.py tests/conftest.py tests/kernel/test_planetary_nodes_repository.py
git commit -m "feat: add planetary_nodes table, model, and repository"
```

---

### Task 2: Mass, brightness, and visual-class formulas (pure, no DB)

**Files:**
- Create: `kernel/planetarium_physics.py`
- Test: `tests/kernel/test_planetarium_physics.py`

**Interfaces:**
- Consumes: nothing (pure functions, no DB, no imports from Task 1).
- Produces: `normalize(values: dict[str, float]) -> dict[str, float]`, `mass_percentiles(masses: dict[str, float]) -> dict[str, float]`, `compute_mass(*, normalized_revision, normalized_edge, normalized_contradiction, normalized_pin) -> float`, `classify_visual_class(*, mass: float, mass_percentile: float, concept_count: int) -> str`, `compute_brightness(days_since_activity: float) -> float`, `node_radius(normalized_mass: float) -> float`, `color_for_visual_class(visual_class: str) -> str`, `spherical_from_cartesian(x: float, y: float, z: float) -> tuple[float, float]` (returns `theta, phi`). Task 4's orchestration calls all of these directly.

- [ ] **Step 1: Write the failing tests**

Create `tests/kernel/test_planetarium_physics.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/kernel/test_planetarium_physics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kernel.planetarium_physics'`

- [ ] **Step 3: Implement the physics module**

Create `kernel/planetarium_physics.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/kernel/test_planetarium_physics.py -v`
Expected: `14 passed`

- [ ] **Step 5: Commit**

```bash
git add kernel/planetarium_physics.py tests/kernel/test_planetarium_physics.py
git commit -m "feat: add Planetarium mass/brightness/visual-class formulas"
```

---

### Task 3: UMAP spatial projection (pure, no DB)

**Files:**
- Modify: `pyproject.toml` (add `umap-learn` dependency)
- Create: `kernel/planetarium_projection.py`
- Test: `tests/kernel/test_planetarium_projection.py`

**Interfaces:**
- Consumes: nothing from Tasks 1-2.
- Produces: `project_concepts(embeddings: dict[UUID, list[float]]) -> dict[UUID, tuple[float, float, float]]`. Task 4's orchestration calls this with one averaged embedding per concept.

- [ ] **Step 1: Add the dependency and install it**

In `pyproject.toml`, in `[project] dependencies`, after `"openai>=2.0,<3.0",`, add:

```toml
    "umap-learn>=0.5,<0.6",
```

Run: `pip install -e ".[dev]"`
Expected: install succeeds, pulling in `numpy`, `scikit-learn`, `scipy`, `numba`, `pynndescent` as transitive dependencies.

- [ ] **Step 2: Write the failing tests**

Create `tests/kernel/test_planetarium_projection.py`:

```python
from __future__ import annotations

from uuid import uuid4

from kernel.planetarium_projection import (
    MIN_CONCEPTS_FOR_UMAP,
    UMAP_FALLBACK_JITTER,
    project_concepts,
)


def _embedding(seed: float) -> list[float]:
    return [seed, seed * 2, seed * 3, seed * 4]


def test_project_concepts_empty_returns_empty():
    assert project_concepts({}) == {}


def test_project_concepts_below_minimum_uses_jittered_origin():
    ids = [uuid4() for _ in range(MIN_CONCEPTS_FOR_UMAP - 1)]
    embeddings = {cid: _embedding(float(i)) for i, cid in enumerate(ids)}

    result = project_concepts(embeddings)

    assert set(result.keys()) == set(ids)
    for i, cid in enumerate(ids):
        assert result[cid] == (i * UMAP_FALLBACK_JITTER, 0.0, 0.0)


def test_project_concepts_runs_umap_above_minimum_and_is_deterministic():
    ids = [uuid4() for _ in range(10)]
    embeddings = {cid: _embedding(float(i)) for i, cid in enumerate(ids)}

    first = project_concepts(embeddings)
    second = project_concepts(embeddings)

    assert set(first.keys()) == set(ids)
    for cid in ids:
        assert first[cid] == second[cid]
        assert len(first[cid]) == 3
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/kernel/test_planetarium_projection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kernel.planetarium_projection'`

- [ ] **Step 4: Implement the projection module**

Create `kernel/planetarium_projection.py`:

```python
from __future__ import annotations

from uuid import UUID

import numpy as np
import umap

UMAP_RANDOM_STATE = 42
UMAP_N_NEIGHBORS_DEFAULT = 15
MIN_CONCEPTS_FOR_UMAP = 3
UMAP_FALLBACK_JITTER = 0.1

PROJECTION_ALGORITHM = "umap"
PROJECTION_VERSION = "v1"


def project_concepts(
    embeddings: dict[UUID, list[float]],
) -> dict[UUID, tuple[float, float, float]]:
    """Maps each concept_id to (x, y, z). Below MIN_CONCEPTS_FOR_UMAP total
    embeddable concepts, UMAP has too few neighbors to run meaningfully —
    each concept is placed near the origin with a small deterministic jitter
    (by insertion order) so they don't exactly overlap."""
    if len(embeddings) < MIN_CONCEPTS_FOR_UMAP:
        return {
            concept_id: (index * UMAP_FALLBACK_JITTER, 0.0, 0.0)
            for index, concept_id in enumerate(embeddings)
        }

    concept_ids = list(embeddings.keys())
    matrix = np.array([embeddings[cid] for cid in concept_ids])
    n_neighbors = min(UMAP_N_NEIGHBORS_DEFAULT, len(concept_ids) - 1)
    reducer = umap.UMAP(
        n_components=3, random_state=UMAP_RANDOM_STATE, n_neighbors=n_neighbors
    )
    coords = reducer.fit_transform(matrix)
    return {
        concept_id: (float(coords[i][0]), float(coords[i][1]), float(coords[i][2]))
        for i, concept_id in enumerate(concept_ids)
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/kernel/test_planetarium_projection.py -v`
Expected: `3 passed` (the UMAP-invoking test takes a few seconds — UMAP has real per-call overhead even on 10 points).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml kernel/planetarium_projection.py tests/kernel/test_planetarium_projection.py
git commit -m "feat: add UMAP spatial projection for the Planetarium"
```

---

### Task 4: Concept embedding lookup and rebuild orchestration

**Files:**
- Modify: `kernel/db/semantic_vectors.py` (add `list_for_concept`)
- Create: `kernel/planetarium.py`
- Test: `tests/kernel/test_planetarium.py`

**Interfaces:**
- Consumes: `PlanetaryNodeRepository.replace_all_for_user` (Task 1), everything from `kernel/planetarium_physics.py` (Task 2), `project_concepts` + `PROJECTION_ALGORITHM`/`PROJECTION_VERSION` (Task 3), plus existing `ConceptRepository.list`, `RevisionRepository.list`, `ClaimConceptEdgeRepository.list_for_concept`, `ContradictionRepository.list`, `ImportanceSignalRepository.list_for_target`.
- Produces: `async def rebuild_planetarium(conn: AsyncConnection, user_id: str | UUID) -> list[PlanetaryNode]` (`kernel/planetarium.py`) — Task 5's worker actor calls this directly.

- [ ] **Step 1: Write the failing test for the new repository method**

Create `tests/kernel/test_semantic_vectors_list_for_concept.py`:

```python
from __future__ import annotations

import pytest

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.observations import ObservationRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository


def _pad(v: list[float]) -> list[float]:
    return v + [0.0] * (1536 - len(v))


@pytest.mark.asyncio
async def test_list_for_concept_returns_only_linked_vectors(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "planetarium-test")
        await SourceRepository(conn).mark_verified(source.id)
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Alpha matters."}], source.id, user_id
        )
        claim = await ClaimRepository(conn).create(
            user_id=user_id,
            source_id=source.id,
            observation_id=obs_id,
            claim_text="Alpha matters.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert claim is not None
        concept = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="Alpha", concept_type="entity"
        )
        assert concept is not None
        candidate = await ConceptCandidateRepository(conn).create(
            user_id=user_id,
            source_id=source.id,
            claim_id=claim.id,
            candidate_name="Alpha",
            concept_type="entity",
            rationale=None,
            confidence=0.9,
            extraction_method="test",
            model_name=None,
            prompt_version=None,
        )
        await ClaimConceptEdgeRepository(conn).create(
            user_id=user_id,
            claim_id=claim.id,
            concept_id=concept.id,
            concept_candidate_id=candidate.id,
            confidence=0.9,
        )
        await SemanticVectorRepository(conn).create(
            user_id=user_id, claim_id=claim.id, embedding=_pad([1.0, 2.0]), model_name="fake"
        )

        linked = await SemanticVectorRepository(conn).list_for_concept(concept.id)
        other_concept = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="Beta", concept_type="entity"
        )
        assert other_concept is not None
        unlinked = await SemanticVectorRepository(conn).list_for_concept(other_concept.id)

    assert len(linked) == 1
    assert linked[0].claim_id == claim.id
    assert unlinked == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/kernel/test_semantic_vectors_list_for_concept.py -v`
Expected: FAIL with `AttributeError: 'SemanticVectorRepository' object has no attribute 'list_for_concept'`

- [ ] **Step 3: Implement `list_for_concept`**

In `kernel/db/semantic_vectors.py`, after `get_for_claim`, add:

```python
    async def list_for_concept(self, concept_id: str | UUID) -> list[SemanticVector]:
        rows = (
            await self.conn.execute(
                text(
                    f"""
                    SELECT sv.id, sv.user_id, sv.claim_id, sv.model_name, sv.created_at,
                           sv.embedding::text AS embedding
                    FROM semantic_vectors sv
                    JOIN claim_concept_edges cce ON cce.claim_id = sv.claim_id
                    WHERE cce.concept_id = :concept_id
                    """
                ),
                {"concept_id": str(concept_id)},
            )
        ).mappings().all()
        return [SemanticVector.from_row(_as_mapping(r)) for r in rows]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/kernel/test_semantic_vectors_list_for_concept.py -v`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add kernel/db/semantic_vectors.py tests/kernel/test_semantic_vectors_list_for_concept.py
git commit -m "feat: add SemanticVectorRepository.list_for_concept"
```

- [ ] **Step 6: Write the failing integration test for `rebuild_planetarium`**

Create `tests/kernel/test_planetarium.py`:

```python
from __future__ import annotations

import pytest

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.importance_signals import ImportanceSignalRepository
from kernel.db.observations import ObservationRepository
from kernel.db.planetary_nodes import PlanetaryNodeRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from kernel.planetarium import rebuild_planetarium


def _pad(v: list[float]) -> list[float]:
    return v + [0.0] * (1536 - len(v))


async def _seed_concept(conn, user_id, name: str, seed: float):  # type: ignore[no-untyped-def]
    source = await SourceRepository(conn).create(user_id, "json", f"planetarium-{name}")
    await SourceRepository(conn).mark_verified(source.id)
    [obs_id] = await ObservationRepository(conn).bulk_insert(
        [{"content": f"{name} matters."}], source.id, user_id
    )
    claim = await ClaimRepository(conn).create(
        user_id=user_id,
        source_id=source.id,
        observation_id=obs_id,
        claim_text=f"{name} matters.",
        claim_type="fact",
        assertion_type="reality",
        confidence=0.9,
        extraction_method="test",
        model_name="fake",
        prompt_version="v1",
    )
    concept = await ConceptRepository(conn).create(
        user_id=user_id, concept_name=name, concept_type="entity"
    )
    candidate = await ConceptCandidateRepository(conn).create(
        user_id=user_id,
        source_id=source.id,
        claim_id=claim.id,
        candidate_name=name,
        concept_type="entity",
        rationale=None,
        confidence=0.9,
        extraction_method="test",
        model_name=None,
        prompt_version=None,
    )
    await ClaimConceptEdgeRepository(conn).create(
        user_id=user_id,
        claim_id=claim.id,
        concept_id=concept.id,
        concept_candidate_id=candidate.id,
        confidence=0.9,
    )
    await SemanticVectorRepository(conn).create(
        user_id=user_id,
        claim_id=claim.id,
        embedding=_pad([seed, seed * 2]),
        model_name="fake",
    )
    return concept, claim


@pytest.mark.asyncio
async def test_rebuild_planetarium_with_no_concepts_produces_no_nodes(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        nodes = await rebuild_planetarium(conn, user_id)
    assert nodes == []


@pytest.mark.asyncio
async def test_rebuild_planetarium_gives_higher_mass_to_more_active_concept(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        quiet_concept, _ = await _seed_concept(conn, user_id, "Quiet", 1.0)
        busy_concept, busy_claim = await _seed_concept(conn, user_id, "Busy", 2.0)

        # Give the busy concept extra revisions, an extra edge's worth of
        # contradiction, and an importance pin — the quiet concept gets none.
        await ImportanceSignalRepository(conn).create(
            user_id=user_id, target_type="concept", target_id=busy_concept.id
        )
        other_source = await SourceRepository(conn).create(user_id, "json", "planetarium-busy-2")
        await SourceRepository(conn).mark_verified(other_source.id)
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Busy conflicts."}], other_source.id, user_id
        )
        other_claim = await ClaimRepository(conn).create(
            user_id=user_id,
            source_id=other_source.id,
            observation_id=obs_id,
            claim_text="Busy conflicts.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        assert other_claim is not None
        await ContradictionRepository(conn).create(
            user_id=user_id,
            concept_id=busy_concept.id,
            claim_a_id=busy_claim.id,
            claim_b_id=other_claim.id,
            similarity=0.95,
            rationale="test contradiction",
        )

        nodes = await rebuild_planetarium(conn, user_id)
        node_by_concept = {n.concept_id: n for n in nodes}

    assert len(nodes) == 2
    assert node_by_concept[busy_concept.id].mass > node_by_concept[quiet_concept.id].mass


@pytest.mark.asyncio
async def test_rebuild_planetarium_replaces_rather_than_duplicates(make_user):
    user_id = await make_user()
    async with session(user_id) as conn:
        await _seed_concept(conn, user_id, "Alpha", 1.0)
        await rebuild_planetarium(conn, user_id)
        second = await rebuild_planetarium(conn, user_id)
        stored = await PlanetaryNodeRepository(conn).list_for_user(user_id)

    assert len(second) == 1
    assert len(stored) == 1
```

- [ ] **Step 7: Run the test to verify it fails**

Run: `pytest tests/kernel/test_planetarium.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kernel.planetarium'`

- [ ] **Step 8: Implement `rebuild_planetarium`**

Create `kernel/planetarium.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import numpy as np
from sqlalchemy.ext.asyncio import AsyncConnection

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.contradictions import ContradictionRepository
from kernel.db.importance_signals import ImportanceSignalRepository
from kernel.db.planetary_nodes import PlanetaryNodeRepository
from kernel.db.revisions import RevisionRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.models import PlanetaryNode
from kernel.planetarium_physics import (
    MASS_FORMULA_VERSION,
    classify_visual_class,
    color_for_visual_class,
    compute_brightness,
    compute_mass,
    mass_percentiles,
    node_radius,
    normalize,
    spherical_from_cartesian,
)
from kernel.planetarium_projection import (
    PROJECTION_ALGORITHM,
    PROJECTION_VERSION,
    project_concepts,
)

# Generous cap on rows fetched per concept per related table — a personal
# archive's per-concept revision/edge/contradiction/pin counts are expected
# to stay far below this; it exists so the query has an explicit LIMIT
# rather than none, matching every other paginated repository method here.
MAX_ROWS_PER_CONCEPT = 10_000


async def rebuild_planetarium(conn: AsyncConnection, user_id: str | UUID) -> list[PlanetaryNode]:
    concepts = await ConceptRepository(conn).list(limit=MAX_ROWS_PER_CONCEPT)
    if not concepts:
        return await PlanetaryNodeRepository(conn).replace_all_for_user(user_id, [])

    revision_repo = RevisionRepository(conn)
    edge_repo = ClaimConceptEdgeRepository(conn)
    contradiction_repo = ContradictionRepository(conn)
    signal_repo = ImportanceSignalRepository(conn)
    vector_repo = SemanticVectorRepository(conn)

    revision_counts: dict[str, float] = {}
    edge_counts: dict[str, float] = {}
    contradiction_counts: dict[str, float] = {}
    pin_counts: dict[str, float] = {}
    days_since_activity: dict[str, float] = {}
    embeddings: dict[UUID, list[float]] = {}
    now = datetime.now(UTC)

    for concept in concepts:
        cid = str(concept.id)
        revisions = await revision_repo.list(concept_id=concept.id, limit=MAX_ROWS_PER_CONCEPT)
        concept_edges = await edge_repo.list_for_concept(concept.id)
        contradictions = await contradiction_repo.list(
            concept_id=concept.id, limit=MAX_ROWS_PER_CONCEPT
        )
        pins = await signal_repo.list_for_target("concept", concept.id)
        vectors = await vector_repo.list_for_concept(concept.id)

        revision_counts[cid] = float(len(revisions))
        edge_counts[cid] = float(len(concept_edges))
        contradiction_counts[cid] = float(len(contradictions))
        pin_counts[cid] = float(len(pins))
        if vectors:
            embeddings[concept.id] = list(np.mean([v.embedding for v in vectors], axis=0))

        timestamps = (
            [concept.created_at]
            + [r.created_at for r in revisions]
            + [e.created_at for e in concept_edges]
            + [c.created_at for c in contradictions]
            + [p.created_at for p in pins]
            + [v.created_at for v in vectors]
        )
        days_since_activity[cid] = (now - max(timestamps)).total_seconds() / 86400.0

    normalized_revision = normalize(revision_counts)
    normalized_edge = normalize(edge_counts)
    normalized_contradiction = normalize(contradiction_counts)
    normalized_pin = normalize(pin_counts)

    masses = {
        cid: compute_mass(
            normalized_revision=normalized_revision[cid],
            normalized_edge=normalized_edge[cid],
            normalized_contradiction=normalized_contradiction[cid],
            normalized_pin=normalized_pin[cid],
        )
        for cid in revision_counts
    }
    normalized_mass = normalize(masses)
    percentiles = mass_percentiles(masses)
    positions = project_concepts(embeddings)

    nodes = []
    for concept in concepts:
        cid = str(concept.id)
        x, y, z = positions.get(concept.id, (0.0, 0.0, 0.0))
        theta, phi = spherical_from_cartesian(x, y, z)
        visual_class = classify_visual_class(
            mass=masses[cid], mass_percentile=percentiles[cid], concept_count=len(concepts)
        )
        nodes.append(
            {
                "concept_id": concept.id,
                "x": x,
                "y": y,
                "z": z,
                "theta": theta,
                "phi": phi,
                "radius": node_radius(normalized_mass[cid]),
                "mass": masses[cid],
                "brightness": compute_brightness(days_since_activity[cid]),
                "color": color_for_visual_class(visual_class),
                "visual_class": visual_class,
                "projection_version": f"{MASS_FORMULA_VERSION}/{PROJECTION_VERSION}",
                "projection_algorithm": PROJECTION_ALGORITHM,
            }
        )
    return await PlanetaryNodeRepository(conn).replace_all_for_user(user_id, nodes)
```

- [ ] **Step 9: Run the test to verify it passes**

Run: `pytest tests/kernel/test_planetarium.py -v`
Expected: `3 passed`

- [ ] **Step 10: Commit**

```bash
git add kernel/planetarium.py tests/kernel/test_planetarium.py
git commit -m "feat: implement rebuild_planetarium orchestration"
```

---

### Task 5: Worker wiring

**Files:**
- Create: `worker/tasks/project_planetarium.py`
- Test: `tests/worker/test_project_planetarium.py`

**Interfaces:**
- Consumes: `rebuild_planetarium` (Task 4), `JobRepository` (existing), `worker.broker.get_broker`/`run_actor` (existing), `worker.tasks.healing.HEAL_DELAY_MS`/`next_heal_generation` (existing).
- Produces: `project_planetarium` dramatiq actor and `heal_project_planetarium` dramatiq actor — Plan 2's API endpoint enqueues `project_planetarium.send(user_id, str(job.id))` after creating a `Job` row with `job_type="project_planetarium"`.

- [ ] **Step 1: Write the failing test**

Create `tests/worker/test_project_planetarium.py`:

```python
from __future__ import annotations

import pytest

from kernel.db.claim_concept_edges import ClaimConceptEdgeRepository
from kernel.db.claims import ClaimRepository
from kernel.db.concept_candidates import ConceptCandidateRepository
from kernel.db.concepts import ConceptRepository
from kernel.db.jobs import JobRepository
from kernel.db.observations import ObservationRepository
from kernel.db.semantic_vectors import SemanticVectorRepository
from kernel.db.session import session
from kernel.db.sources import SourceRepository
from worker.tasks.healing import MAX_HEAL_GENERATIONS
from worker.tasks.project_planetarium import _heal_project_planetarium, _project_planetarium


def _pad(v: list[float]) -> list[float]:
    return v + [0.0] * (1536 - len(v))


async def _seed_one_concept(user_id):  # type: ignore[no-untyped-def]
    async with session(user_id) as conn:
        source = await SourceRepository(conn).create(user_id, "json", "worker-test")
        await SourceRepository(conn).mark_verified(source.id)
        [obs_id] = await ObservationRepository(conn).bulk_insert(
            [{"content": "Alpha matters."}], source.id, user_id
        )
        claim = await ClaimRepository(conn).create(
            user_id=user_id,
            source_id=source.id,
            observation_id=obs_id,
            claim_text="Alpha matters.",
            claim_type="fact",
            assertion_type="reality",
            confidence=0.9,
            extraction_method="test",
            model_name="fake",
            prompt_version="v1",
        )
        concept = await ConceptRepository(conn).create(
            user_id=user_id, concept_name="Alpha", concept_type="entity"
        )
        candidate = await ConceptCandidateRepository(conn).create(
            user_id=user_id,
            source_id=source.id,
            claim_id=claim.id,
            candidate_name="Alpha",
            concept_type="entity",
            rationale=None,
            confidence=0.9,
            extraction_method="test",
            model_name=None,
            prompt_version=None,
        )
        await ClaimConceptEdgeRepository(conn).create(
            user_id=user_id,
            claim_id=claim.id,
            concept_id=concept.id,
            concept_candidate_id=candidate.id,
            confidence=0.9,
        )
        await SemanticVectorRepository(conn).create(
            user_id=user_id, claim_id=claim.id, embedding=_pad([1.0, 2.0]), model_name="fake"
        )
        job = await JobRepository(conn).create(user_id, "project_planetarium")
    return job


@pytest.mark.asyncio
async def test_project_planetarium_completes_and_reports_node_count(make_user):
    user_id = await make_user()
    job = await _seed_one_concept(user_id)

    await _project_planetarium(str(user_id), str(job.id))

    async with session(user_id) as conn:
        done = await JobRepository(conn).get(job.id)
    assert done is not None
    assert done.status == "completed"
    assert done.result == {"node_count": 1}


@pytest.mark.asyncio
async def test_project_planetarium_records_failure_on_exception(make_user, monkeypatch):
    user_id = await make_user()
    job = await _seed_one_concept(user_id)

    async def _boom(conn, user_id):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr("worker.tasks.project_planetarium.rebuild_planetarium", _boom)

    with pytest.raises(RuntimeError):
        await _project_planetarium(str(user_id), str(job.id))

    async with session(user_id) as conn:
        failed = await JobRepository(conn).get(job.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.attempts == 1


@pytest.mark.asyncio
async def test_heal_project_planetarium_creates_fresh_job_and_resends(make_user, monkeypatch):
    user_id = await make_user()
    job = await _seed_one_concept(user_id)

    sent: dict = {}

    def _fake_send_with_options(*, args, delay, heal_generation):  # type: ignore[no-untyped-def]
        sent["args"] = args
        sent["delay"] = delay
        sent["heal_generation"] = heal_generation

    monkeypatch.setattr(
        "worker.tasks.project_planetarium.project_planetarium.send_with_options",
        _fake_send_with_options,
    )

    original_message = {"args": (str(user_id), str(job.id)), "options": {}}
    await _heal_project_planetarium(original_message, {})

    assert sent["heal_generation"] == 1
    assert sent["args"][0] == str(user_id)
    new_job_id = sent["args"][1]
    assert new_job_id != str(job.id)


@pytest.mark.asyncio
async def test_heal_project_planetarium_stops_at_generation_cap(make_user):
    user_id = await make_user()
    job = await _seed_one_concept(user_id)
    original_message = {
        "args": (str(user_id), str(job.id)),
        "options": {"heal_generation": MAX_HEAL_GENERATIONS},
    }
    # No monkeypatch on send_with_options — if the cap isn't respected, this
    # call would try to actually enqueue via the real broker and fail loudly.
    await _heal_project_planetarium(original_message, {})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/worker/test_project_planetarium.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'worker.tasks.project_planetarium'`

- [ ] **Step 3: Implement the worker task**

Create `worker/tasks/project_planetarium.py`:

```python
from __future__ import annotations

from typing import Any

import dramatiq

from kernel.db.jobs import JobRepository
from kernel.db.session import session
from kernel.planetarium import rebuild_planetarium
from worker.broker import get_broker, run_actor
from worker.tasks.errors import public_error
from worker.tasks.healing import HEAL_DELAY_MS, next_heal_generation

get_broker()


async def _project_planetarium(user_id: str, job_id: str) -> None:
    async with session(user_id) as conn:
        await JobRepository(conn).mark_running(job_id)
    try:
        async with session(user_id) as conn:
            nodes = await rebuild_planetarium(conn, user_id)
        async with session(user_id) as conn:
            await JobRepository(conn).mark_completed(job_id, result={"node_count": len(nodes)})
    except Exception as exc:
        async with session(user_id) as conn:
            await JobRepository(conn).record_attempt(job_id, error=public_error(str(exc)))
        raise


# A rebuild recomputes every concept's signals and re-runs UMAP over the
# whole archive — heavier than embedding one batch, but still bounded by a
# personal archive's concept count rather than an open-ended crawl.
PROJECT_PLANETARIUM_TIME_LIMIT_MS = 30 * 60 * 1000


@dramatiq.actor(
    queue_name="extraction",
    max_retries=3,
    on_retry_exhausted="heal_project_planetarium",
    time_limit=PROJECT_PLANETARIUM_TIME_LIMIT_MS,
)
def project_planetarium(user_id: str, job_id: str) -> None:
    run_actor(_project_planetarium(user_id, job_id))


async def _heal_project_planetarium(
    original_message: dict[str, Any], stats: dict[str, Any]
) -> None:
    generation = next_heal_generation(original_message)
    if generation is None:
        return
    user_id, _old_job_id = original_message["args"]
    async with session(user_id) as conn:
        new_job = await JobRepository(conn).create(user_id, "project_planetarium")
    project_planetarium.send_with_options(
        args=(user_id, str(new_job.id)),
        delay=HEAL_DELAY_MS,
        heal_generation=generation,
    )


@dramatiq.actor(queue_name="extraction")
def heal_project_planetarium(original_message: dict[str, Any], stats: dict[str, Any]) -> None:
    run_actor(_heal_project_planetarium(original_message, stats))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/worker/test_project_planetarium.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add worker/tasks/project_planetarium.py tests/worker/test_project_planetarium.py
git commit -m "feat: wire the Planetarium rebuild into a dramatiq worker actor"
```

---

### Task 6: Docs

**Files:**
- Modify: `README.md` (add a "Phase 4 Planetarium Engine" section)

**Interfaces:** none — documentation only.

- [ ] **Step 1: Add the README section**

In `README.md`, after the "Phase 3 Custodian Core" section (or whichever Phase 3 section is last) and before "## Project Layout", add:

```markdown
## Phase 4 Planetarium Engine

The Planetarium projects each concept into a 3D scene: a spatial position
from UMAP over its claims' embeddings, a "mass" from a versioned weighted
sum over four real signals (revision count, claim-concept edge count,
contradiction count, importance-signal pin count), and a visual
classification (`planet` by default, `black_hole` for the top decile by
mass). `kernel.planetarium.rebuild_planetarium(conn, user_id)` computes and
replaces a user's `planetary_nodes` rows in one transaction — it's a
disposable cache, never a source of truth. Runs as a `project_planetarium`
dramatiq job, same `Job`/healing pattern as every other worker task. No API
endpoint or frontend yet — see
[docs/superpowers/specs/2026-07-10-planetarium-engine-design.md](docs/superpowers/specs/2026-07-10-planetarium-engine-design.md)
and the Phase 4 roadmap for Plans 2-4.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: document the Planetarium Engine"
```

---

## Final Verification

- [ ] Run the full test suite: `pytest`
- [ ] Run `alembic check` to confirm no unapplied migrations.
- [ ] Run `ruff check kernel/ worker/` and `mypy kernel/ worker/`.
- [ ] Confirm `pip show umap-learn` succeeds in the project's `.venv`.

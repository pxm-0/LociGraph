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

_NODE_FIELDS = (
    "concept_id", "x", "y", "z", "theta", "phi", "radius", "mass",
    "brightness", "color", "visual_class", "projection_version", "projection_algorithm",
)
# Rows per INSERT — keeps bind-parameter count (batch size * len(_NODE_FIELDS))
# well under Postgres's ~65535 parameter limit while still turning what used
# to be one round trip per node into a handful of round trips per rebuild.
_INSERT_BATCH_SIZE = 500


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
        for start in range(0, len(nodes), _INSERT_BATCH_SIZE):
            batch = nodes[start : start + _INSERT_BATCH_SIZE]
            params: dict[str, Any] = {"user_id": str(user_id)}
            row_placeholders = []
            for i, node in enumerate(batch):
                row_placeholders.append(
                    "(:user_id, " + ", ".join(f":{field}_{i}" for field in _NODE_FIELDS) + ")"
                )
                for field in _NODE_FIELDS:
                    value = node[field]
                    params[f"{field}_{i}"] = str(value) if field == "concept_id" else value
            rows = (
                await self.conn.execute(
                    text(
                        f"""
                        INSERT INTO planetary_nodes (user_id, {", ".join(_NODE_FIELDS)})
                        VALUES {", ".join(row_placeholders)}
                        RETURNING {_COLUMNS}
                        """
                    ),
                    params,
                )
            ).mappings().all()
            created.extend(PlanetaryNode.from_row(_as_mapping(r)) for r in rows)
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

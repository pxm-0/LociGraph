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

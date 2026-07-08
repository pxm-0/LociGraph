from __future__ import annotations

from fastapi import FastAPI

from backend.app.api import (
    auth,
    claims,
    concepts,
    contradictions,
    dashboard,
    jobs,
    observations,
    search,
    sources,
)


def create_app() -> FastAPI:
    app = FastAPI(title="LociGraph")
    app.include_router(auth.router)
    app.include_router(sources.router)
    app.include_router(observations.router)
    app.include_router(jobs.router)
    app.include_router(dashboard.router)
    app.include_router(claims.router)
    app.include_router(concepts.router)
    app.include_router(contradictions.router)
    app.include_router(search.router)
    return app


app = create_app()

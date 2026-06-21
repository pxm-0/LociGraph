from __future__ import annotations

from fastapi import FastAPI

from backend.app.api import auth


def create_app() -> FastAPI:
    app = FastAPI(title="LociGraph")
    app.include_router(auth.router)
    return app


app = create_app()

from fastapi import FastAPI

from kl_server.api.routes import router
from kl_server.api.ws import router as ws_router


def create_app() -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.include_router(router)
    app.include_router(ws_router)
    return app

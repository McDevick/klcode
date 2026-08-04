from fastapi import FastAPI
from fastapi.responses import JSONResponse

from kl_server.api.routes import router
from kl_server.api.ws import router as ws_router


def create_app(auth_token: str | None = None) -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def auth_middleware(request, call_next):
        if auth_token:
            if request.headers.get("Authorization") != f"Bearer {auth_token}":
                return JSONResponse(status_code=401, content={"detail": "unauthorized"})
        return await call_next(request)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.include_router(router)
    app.include_router(ws_router)
    return app

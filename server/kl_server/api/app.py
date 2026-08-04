import secrets

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from kl_server.api.routes import router
from kl_server.api.ws import configure_auth, router as ws_router


def create_app(auth_token: str | None = None) -> FastAPI:
    configure_auth(auth_token)
    app = FastAPI()

    @app.middleware("http")
    async def auth_middleware(request, call_next):
        if auth_token:
            header = request.headers.get("Authorization", "")
            if not secrets.compare_digest(header, f"Bearer {auth_token}"):
                return JSONResponse(status_code=401, content={"detail": "unauthorized"})
        return await call_next(request)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.include_router(router)
    app.include_router(ws_router)
    return app

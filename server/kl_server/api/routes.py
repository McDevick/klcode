from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/ping")
def ping():
    return {"status": "pong"}

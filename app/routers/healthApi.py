from fastapi import APIRouter
from datetime import datetime, timezone


router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}




from fastapi import APIRouter
from app.core.database import ping_database

router = APIRouter(prefix="/health", tags=["health"])

@router.get("")
def health_check():
    ping_database()
    return {"status": "ok", "database": "ok", "service": "nuvly-backend"}

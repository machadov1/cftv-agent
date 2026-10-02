from fastapi import APIRouter

from backend import servidores

router = APIRouter(prefix="/servidores", tags=["servidores"])


@router.get("/status")
def status():
    return servidores.status()

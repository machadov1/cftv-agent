from fastapi import APIRouter
from backend import sync

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/status")
def sync_status():
    return sync.status()


@router.post("")
def sync_now():
    """Busca agora os incidentes novos da fila AMS-TI-CFTV (somente leitura no ServiceNow)."""
    return sync.run_sync()

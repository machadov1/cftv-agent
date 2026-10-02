from fastapi import APIRouter, HTTPException
from backend import backlog
from backend.servicenow_api import SNAuthError

router = APIRouter(prefix="/backlog", tags=["backlog"])


@router.get("")
def get_backlog(force: bool = False):
    """Backlog aberto das filas CFTV com prazos (somente leitura no ServiceNow)."""
    try:
        return backlog.get_backlog(force)
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar no cabeçalho")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao ler o backlog: {e}")

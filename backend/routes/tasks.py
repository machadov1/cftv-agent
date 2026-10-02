from fastapi import APIRouter, HTTPException
from backend import tasks
from backend.servicenow_api import SNAuthError

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def get_tasks(force: bool = False):
    """TASKs de acesso a imagens abertas nas filas CFTV (somente leitura no ServiceNow)."""
    try:
        return tasks.get_tasks(force)
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar no cabeçalho")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao ler as TASKs: {e}")


@router.get("/volumetria")
def get_tasks_volumetria(meses: int = 5, force: bool = False):
    """TASKs de acesso: abertas x encerradas por mês (somente leitura, cache de 10 min)."""
    from backend import volumetria
    try:
        return volumetria.serie("tasks", max(1, min(meses, 12)), force)
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar no cabeçalho")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao ler volumetria: {e}")

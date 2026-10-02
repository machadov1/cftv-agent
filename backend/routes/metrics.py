from fastapi import APIRouter
from backend.db import get_metrics, get_breakdown, get_insights
from backend.models import MetricsOut

router = APIRouter(prefix="/metrics", tags=["metrics"])

@router.get("")
def get_dashboard_metrics() -> MetricsOut:
    """Retornar métricas do dashboard"""
    return get_metrics()

@router.get("/insights")
def get_metrics_insights():
    """Padrões: informais por unidade, recorrência (título e câmera), temas como elétrica, alertas"""
    return get_insights()

@router.get("/breakdown")
def get_metrics_breakdown():
    """Distribuição por localidade, status e origem da decisão"""
    return get_breakdown()

@router.get("/volumetria")
def get_metrics_volumetria(meses: int = 5, force: bool = False):
    """Incidentes das filas CFTV/A4: entraram x encerrados por mês (somente leitura, cache de 10 min)."""
    from fastapi import HTTPException
    from backend import volumetria
    from backend.servicenow_api import SNAuthError
    try:
        return volumetria.serie("incidentes", max(1, min(meses, 12)), force)
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar no cabeçalho")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao ler volumetria: {e}")

@router.get("/painel")
def get_metrics_painel():
    """Insights acionáveis: backlog do ServiceNow (cache 60 s) + histórico local + planilha de RITMs. Só leitura."""
    from datetime import datetime
    from backend import backlog, controle, db, insights, learning
    avisos = []
    try:
        bl = backlog.get_backlog()
    except Exception as e:  # noqa: BLE001 (ServiceNow fora: o resto do painel continua)
        bl, _ = None, avisos.append(f"Backlog do ServiceNow indisponível: {e}")
    ritm_rows, aviso = controle.read_rows()
    if aviso:
        avisos.append(aviso)
    try:
        sug = learning.sugestoes()
    except Exception:  # noqa: BLE001
        sug = []
    hist = db.history_by_actions(("analise", "aprovado", "editado", "snapshot", "snapshot_anexo",
                                  "nota_encerramento", "ritm"), dias=60)
    out = insights.painel(bl, hist, ritm_rows, db.list_incidents(500), sug, db.list_backlog_snapshots(14),
                          datetime.now(backlog._TZ))
    out["avisos"] = avisos
    out["sn_base"] = backlog.sn_api.base_url  # link direto para o incidente
    return out

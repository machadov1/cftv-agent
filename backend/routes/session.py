from fastapi import APIRouter
from backend.config import config
from backend.sn_session import session

router = APIRouter(prefix="/session", tags=["session"])


@router.get("/status")
def status():
    if config.SERVICENOW_MOCK:
        return {"connected": False, "busy": None, "user": None, "mock": True,
                "message": "Modo mock: nenhuma sessão é usada.", "checked_at": None, "instance": None}
    return {**session.status(), "mock": False, "instance": config.SERVICENOW_INSTANCE}


@router.post("/login")
def login():
    """Abre a janela do navegador para login manual (SSO/MFA)."""
    if not config.SERVICENOW_MOCK and not session.busy:
        session.login()
    return status()


@router.post("/refresh")
def refresh():
    """Tenta renovar em segundo plano com o perfil salvo."""
    if not config.SERVICENOW_MOCK and not session.busy:
        session.refresh()
    return status()

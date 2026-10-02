from typing import Optional
from fastapi import APIRouter
from backend import db

router = APIRouter(prefix="/history", tags=["history"])

@router.get("")
def list_history(limit: int = 100, incident_number: Optional[str] = None,
                 acao: Optional[str] = None):
    """Histórico de ações (analise / aprovado / editado)"""
    return db.list_history(limit, incident_number.upper() if incident_number else None, acao)

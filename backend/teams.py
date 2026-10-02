"""Rascunho de mensagem no Teams (skill operador-cftv, seção 13). NUNCA envia.

Só monta a mensagem e o deep link; abrir o link pré-preenche o chat e o Victor revisa e envia.
"""
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # Windows sem tzdata: Brasil sem horário de verão desde 2019
    _TZ = timezone(timedelta(hours=-3))

from backend.ritm import _ANALISE


def saudacao(agora: datetime | None = None) -> str:
    h = (agora or datetime.now(_TZ)).hour
    return "Bom dia" if h < 12 else "Boa tarde" if h < 18 else "Boa noite"


def primeiro_nome(caller: str) -> str:
    """'Costa, Ericon Sampaio' -> 'Ericon'; 'Ericon Costa' -> 'Ericon'."""
    parte = caller.split(",", 1)[1] if "," in caller else caller
    return (parte.strip().split() or [""])[0].title()


def default_identificado(causa: str, pendencia: str) -> str:
    dep = _ANALISE.get(pendencia, "atuação de outra equipe")
    return f"{causa}. O restabelecimento depende de {dep} pela equipe responsável."


def build_message(inc: str, nome: str, identificado: str, ritm: str, cameras: int, agora: datetime | None = None) -> str:
    alvo = "das câmeras" if cameras > 1 else "da câmera" if cameras == 1 else "do caso"
    return (
        f"{inc}: {saudacao(agora)}, {nome}. Tudo bem?\n\n"
        f"{identificado}\n\n"
        f"Para dar continuidade ao caso, foi aberta a requisição de acompanhamento {ritm}, vinculada a este incidente. "
        f"O acompanhamento seguirá por ela até a normalização {alvo}.\n\n"
        f"Fico à disposição."
    )


def build_message_acesso(inc: str, nome: str, agora: datetime | None = None) -> str:
    """Pedido de acesso às câmeras (skill, fluxo 8). [LINK] fica para o Victor colar o link da requisição."""
    return (
        f"{inc}: {saudacao(agora)}, {nome}. Tudo bem?\n\n"
        "Sobre o seu pedido de acesso às câmeras: por envolver aprovação gerencial (LGPD), o acesso é liberado via "
        "requisição no portal. Segue o link para abrir a solicitação:\n\n"
        "[LINK]\n\n"
        "Fico à disposição."
    )


def build_url(email: str, msg: str) -> str:
    return "https://teams.cloud.microsoft/l/chat/0/0?users=" + quote(email, safe="") + "&message=" + quote(msg, safe="")


def open_draft(url: str) -> None:
    """Abre o chat com a mensagem pré-preenchida no navegador padrão. Não envia nada."""
    os.startfile(url)  # noqa: S606 (Windows)

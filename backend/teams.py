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

from backend import textos


def saudacao(agora: datetime | None = None) -> str:
    h = (agora or datetime.now(_TZ)).hour
    return "Bom dia" if h < 12 else "Boa tarde" if h < 18 else "Boa noite"


def primeiro_nome(caller: str) -> str:
    """'Costa, Ericon Sampaio' -> 'Ericon'; 'Ericon Costa' -> 'Ericon'."""
    parte = caller.split(",", 1)[1] if "," in caller else caller
    return (parte.strip().split() or [""])[0].title()


def _minuscula(t: str) -> str:
    """'Câmeras 399 sem conexão' -> 'câmeras 399 sem conexão' (códigos em maiúsculas ficam como estão)."""
    return t[:1].lower() + t[1:] if t[:2] and not t[:2].isupper() else t


def default_identificado(causa: str, pendencia: str) -> str:
    """O que depende de quem, em linguagem de gente (manual: sem 'pendência vinculada')."""
    return f"O reparo depende {textos.pendencia(pendencia)[2]}."


def build_message(inc: str, nome: str, identificado: str, ritm: str, causa: str = "", agora: datetime | None = None) -> str:
    """Mensagem ao solicitante (manual: Teams/WhatsApp). Só o primeiro nome, saudação pelo período."""
    sobre = f"o incidente {inc}" + (f", {_minuscula(causa.strip().rstrip('.'))}" if causa.strip() else "")
    return (
        f"{saudacao(agora)}, {nome}! Tudo bem?\n\n"
        f"Passando pra te atualizar sobre {sobre}.\n\n"
        f"{identificado.strip()}\n\n"
        f"Para acompanhamento das ações, foi aberta a requisição {ritm}.\n\n"
        "Qualquer dúvida, fico à disposição!"
    )


def build_message_acesso(inc: str, nome: str, agora: datetime | None = None) -> str:
    """Pedido de acesso às câmeras (skill, fluxo 8). [LINK] fica para o Victor colar o link da requisição."""
    return (
        f"{saudacao(agora)}, {nome}! Tudo bem?\n\n"
        f"Passando pra te atualizar sobre o incidente {inc}, de acesso às câmeras.\n\n"
        "A liberação de acesso segue por requisição no portal, porque depende de aprovação gerencial (LGPD). "
        "Segue o link para abertura:\n\n"
        "[LINK]\n\n"
        "Qualquer dúvida, fico à disposição!"
    )


def build_url(email: str, msg: str) -> str:
    return "https://teams.cloud.microsoft/l/chat/0/0?users=" + quote(email, safe="") + "&message=" + quote(msg, safe="")


def open_draft(url: str) -> None:
    """Abre o chat com a mensagem pré-preenchida no navegador padrão. Não envia nada."""
    os.startfile(url)  # noqa: S606 (Windows)

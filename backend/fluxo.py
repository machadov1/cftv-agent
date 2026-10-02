"""Entrada e saída da fila local: uma regra só, a partir do estado real no ServiceNow.

Status local (coluna incidents.status):
- analisado     Entrada: Novo no ServiceNow, na fila geral (AMS-TI-CFTV), sem nota minha. Aguarda primeira tratativa.
- aprovado      Saída: despachado pelo agente (/approve).
- tratado_fora  Saída: saiu da Entrada sem o agente (outro estado, outra fila ou já tem nota minha).
- encerrado     Resolvido/encerrado/cancelado no ServiceNow (6, 7, 24). Fora das duas listas.
Estado 8 é "Aguardando Mudança" (não é encerrado). Só leitura no ServiceNow.
"""
import re

from backend import db
from backend.config import config
from backend.servicenow_api import sn_api

ENTRADA, DESPACHADO, FORA, ENCERRADO = "analisado", "aprovado", "tratado_fora", "encerrado"
SAIDA = (DESPACHADO, FORA)
ESTADO_NOVO = "1"
ESTADOS_ENCERRADOS = {"6", "7", "24"}
# cabeçalho de cada nota no texto exibido: "01/10/2026 17:48:31 - Machado, Victor Alexandre Basilio (Anotações de trabalho)"
_AUTOR = re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2} - (.+?) \((?:Anota|Work note)", re.M)


def autores(work_notes: str | None) -> list[str]:
    """Autores das work notes, da mais nova para a mais velha."""
    return _AUTOR.findall(work_notes or "")


def classificar(sn: dict, atual: str | None, eu: str | None) -> str:
    """Status local a partir do ServiceNow. `sn`: {state, grupo, work_notes}; `eu`: meu nome como aparece nas notas."""
    estado = str(sn.get("state") or "")
    if estado in ESTADOS_ENCERRADOS:
        return ENCERRADO
    if atual == DESPACHADO:
        return DESPACHADO  # saiu pelo agente: continua "despachado" enquanto aberto
    minha_nota = bool(eu) and eu in autores(sn.get("work_notes"))
    if estado != ESTADO_NOVO or (sn.get("grupo") and sn["grupo"] != config.QUEUE_GROUP) or minha_nota:
        return FORA
    return ENTRADA


def reconciliar() -> dict:
    """Confere no ServiceNow (uma consulta por bloco) os incidentes da Entrada e da Saída recente e move cada um
    para o status certo. Devolve {conferidos, mudaram: [(INC, de, para)]}."""
    locais = {r["sys_id"]: r for r in db.incidents_para_reconciliar() if r.get("sys_id")}
    if not locais or config.SERVICENOW_MOCK:
        return {"conferidos": 0, "mudaram": []}
    eu = sn_api.meu_nome()
    mudaram = []
    for sn in sn_api.estado_lote(list(locais)):
        loc = locais.get(sn["sys_id"])
        if not loc:
            continue
        novo = classificar(sn, loc["status"], eu)
        nota = (autores(sn["work_notes"]) or [None])[0]
        db.set_fluxo(loc["incident_number"], novo, sn["state"], sn["grupo_nome"], nota, sn.get("due_date"))
        if novo != loc["status"]:
            mudaram.append((loc["incident_number"], loc["status"], novo))
            db.add_history(loc["incident_number"], "fluxo", f"{loc['status']} → {novo} (SN estado {sn['state']}, "
                                                           f"{sn['grupo_nome'] or 'sem fila'})")
    return {"conferidos": len(locais), "mudaram": mudaram}

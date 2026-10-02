"""Painel de TASKs de acesso a imagens (board 'TASKs' do ServiceNow, tabela sc_task). SOMENTE LEITURA.

O board do time (vtb 9fd807023b6e7a908c9f67dc73e45a83) mostra todas as tarefas de catálogo das filas CFTV; aqui só
entram as de acesso a imagens, que são as que o Victor trata. Os dados da requisição vêm no texto da descrição
("Solicitante : ...", "Área das Câmeras : ...").
"""
import json
import re
import time
from datetime import datetime, timedelta, timezone

from backend.backlog import _TZ, _f, _truthy, _ultima_nota, _utc
from backend.config import ROOT, config
from backend.servicenow_api import sn_api, _check
from backend.sn_session import session

BOARD = "9fd807023b6e7a908c9f67dc73e45a83"
# filtro do board (vtb_board.filter): filas CFTV + FCB-INFRA-CFTV-PEC + A4, fora Concluído (3) e Closed Incomplete (4)
GRUPOS = ("assignment_groupLIKEAMS-TI-CFTV^ORassignment_group=1bcc7ad91bc78290febdeac82d4bcbe8"
          "^ORassignment_groupLIKEAMS-TI-A4")
BOARD_FILTER = f"{GRUPOS}^stateNOT IN3,4"
# itens de catálogo de acesso a imagens (dois ativos + dois antigos, inativos, que ainda podem ter tarefa aberta)
CAT_ITEMS = ("776d895f1b6471504ef531901a4bcb74",  # Solicitação de Acesso as Imagens – CFTV
             "d2e1e2781b3e4a1c8287415fad4bcb80",  # Digifort - Solicitação de acesso a imagens
             "93ff9e381bba4a1c8287415fad4bcb1f", "b3d0aab41bfa4a1c8287415fad4bcb80")
FIELDS = ("sys_id,number,short_description,description,state,assignment_group,assigned_to,assigned_to.user_name,"
          "opened_at,sys_updated_on,request_item,request,cat_item,priority,comments_and_work_notes,u_has_breached")
CACHE_TTL = 60
_cache: dict = {"at": 0.0, "data": None}
# casos pontuais que não devem aparecer no painel: {"TASK...": "motivo"} (editar o arquivo à mão)
OCULTAS_PATH = ROOT / "data" / "tasks_ocultas.json"

# "Localidade : CFTV - Monlevade" -> unidade com o nome usado no resto do painel (cores, filas)
UNIDADE = {"monlevade": "João Monlevade", "joao monlevade": "João Monlevade", "piracicaba": "Piracicaba",
           "resende": "Resende", "barra mansa": "Barra Mansa", "juiz de fora": "Juiz de Fora", "sabara": "Sabará",
           "jaboatao": "Jaboatão", "bauru": "Bauru", "guarulhos": "Guarulhos", "iracemapolis": "Iracemápolis",
           "candeias": "Candeias", "vega do sul": "Vega do Sul", "rio das pedras": "Rio das Pedras",
           "tubarao": "Tubarão", "igarape": "Igarapé", "serra azul": "Serra Azul", "pecem": "Pecém"}
TIPO = {"visualization": "Visualização", "visualizacao": "Visualização", "playback": "Reprodução",
        "export": "Exportação"}
TIPO_FLAG = {"visualizacao": "Visualização", "reproducao": "Reprodução", "exportacao": "Exportação"}
_LINHA = re.compile(r"^\s*([^:\n]{2,40}?)\s*:\s*:?\s*(.*?)\s*$")


def _sem_acento(s: str) -> str:
    return s.lower().translate(str.maketrans("áàâãéêíóôõúç", "aaaaeeiooouc"))


# chaves dos formulários; linha que não começa por uma delas continua o campo anterior (descrição em várias linhas,
# "BM-LOG-C-016 dia 07/08 das 19:00..." não vira chave)
CHAVES = {"solicitante", "departamento", "e-mail", "gerencia", "area das cameras", "localidade", "descricao detalhada",
          "descricao", "observacoes / historico", "tipo", "abrir em nome de outro usuario", "aberto por",
          "solicitado para", "id do usuario", "empresa", "cost center", "justificativa", "visualizacao", "reproducao",
          "exportacao", "area", "localizacao (predio)", "sala", "ramal / faixa de radio", "celular"}


def parse_descricao(texto: str | None) -> dict:
    """'Chave : valor' por linha (o bloco 'Informações da Requisição' da tarefa). Chaves sem acento, minúsculas."""
    out, ultima = {}, None
    for linha in (texto or "").splitlines():
        m = _LINHA.match(linha)
        chave = _sem_acento(m.group(1)).rstrip(":").strip() if m else None
        if chave in CHAVES:
            ultima = chave
            if m.group(2):
                out[chave] = m.group(2)
        elif ultima and linha.strip() and "informações da requisição" not in linha.lower():
            out[ultima] = f"{out.get(ultima, '')} {linha.strip()}".strip()
    return out


def unidade(localidade: str | None) -> str | None:
    if not localidade:
        return None
    limpo = re.sub(r"\s+", " ", re.sub(r"^\s*(?:CFTV\s*-|ArcelorMittal)\s*", "", localidade, flags=re.I)).strip()
    base = _sem_acento(limpo)
    for chave, nome in UNIDADE.items():
        if chave in base:  # "Mina Serra Azul", "Entreposto Igarapé"
            return nome
    return limpo or None


def normalize(r: dict, now: datetime, eu: str | None) -> dict:
    d = parse_descricao(_f(r, "description"))
    aberto = _utc(_f(r, "opened_at", "value"))
    # dois formulários: "Acesso as Imagens – CFTV" (Solicitante, Área das Câmeras, Localidade, Tipo) e
    # "Digifort" de Pecém (Solicitado para, Área, Empresa, Justificativa e um Verdadeiro/Falso por permissão)
    loc = d.get("localidade") or d.get("empresa")
    tipo = d.get("tipo") or ""
    flags = [k.capitalize() for k in ("visualizacao", "reproducao", "exportacao") if _truthy(d.get(k))]
    tipo = TIPO.get(_sem_acento(tipo), tipo) or " + ".join(TIPO_FLAG[f.lower()] for f in flags) or None
    area = d.get("area das cameras") or " · ".join(x for x in (d.get("area"), d.get("localizacao (predio)"), d.get("sala")) if x)
    return {
        "number": _f(r, "number"),
        "sys_id": _f(r, "sys_id", "value"),
        "link": f"https://{config.SERVICENOW_INSTANCE}.service-now.com/sc_task.do?sys_id={_f(r, 'sys_id', 'value')}",
        "ritm": _f(r, "request_item"),
        "req": _f(r, "request"),
        "item": _f(r, "cat_item"),
        "titulo": _f(r, "short_description"),
        "estado": _f(r, "state"),
        "grupo": _f(r, "assignment_group") or "",
        "responsavel": _f(r, "assigned_to") or None,
        "meu": bool(eu) and _f(r, "assigned_to.user_name", "value") == eu,
        "aberto": aberto.isoformat() if aberto else None,
        "idade_dias": (now - aberto).days if aberto else None,
        "atualizado": (_utc(_f(r, "sys_updated_on", "value")) or now).isoformat(),
        "solicitante": d.get("solicitante") or d.get("solicitado para"),
        "email": d.get("e-mail"),
        "gerencia": d.get("gerencia") or d.get("departamento"),
        "area": area or None,
        "localidade": loc,
        "unidade": unidade(loc),
        "tipo": tipo,
        "justificativa": (d.get("descricao detalhada") or d.get("descricao") or d.get("justificativa")
                          or d.get("observacoes / historico")),
        "prioridade": _f(r, "priority"),
        "sla_violado": _truthy(_f(r, "u_has_breached", "value")),
        "ultima_nota": _ultima_nota(_f(r, "comments_and_work_notes")),
    }


def summarize(rows: list[dict]) -> dict:
    def conta(chave):
        c: dict = {}
        for r in rows:
            k = r[chave] or "—"
            c[k] = c.get(k, 0) + 1
        return [{"nome": k, "total": n} for k, n in sorted(c.items(), key=lambda x: -x[1])]
    idades = [r["idade_dias"] for r in rows if r["idade_dias"] is not None]
    return {
        "total": len(rows),
        "sem_responsavel": sum(not r["responsavel"] for r in rows),
        "meus": sum(r["meu"] for r in rows),
        "mais_de_7_dias": sum(i > 7 for i in idades),
        "mais_antiga_dias": max(idades) if idades else None,
        "por_unidade": conta("unidade"),
        "por_responsavel": conta("responsavel"),
        "por_estado": conta("estado"),
    }


def _mock_rows(now: datetime) -> list[dict]:
    def raw(n, ritm, quem, area, loc, resp, user, dias, just):
        op = (now - timedelta(days=dias)).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        desc = (f"\n\n Informações da Requisição\nSolicitante : {quem}\nGerência : SUP PROD\nÁrea das Câmeras : {area}\n"
                f"Localidade : CFTV - {loc}\nDescrição detalhada : {just}\nTipo: : Visualização\n")
        return {"number": n, "sys_id": {"value": f"mock-{n.lower()}"}, "request_item": {"display_value": ritm},
                "short_description": "Tarefa de Execução - Acesso as Imagens – CFTV", "description": desc,
                "state": {"display_value": "Aberto"}, "assignment_group": {"display_value": "AMS-TI-CFTV"},
                "assigned_to": {"display_value": resp}, "assigned_to.user_name": {"value": user},
                "opened_at": {"value": op}, "cat_item": {"display_value": "Solicitação de Acesso as Imagens – CFTV"}}
    return [normalize(x, now, "70199550") for x in [
        raw("TASK9000001", "RITM9000001", "Benedito, Renan", "GAPLA 3", "Monlevade", "", "", 1, "Acesso às câmeras do laminador 3."),
        raw("TASK9000002", "RITM9000002", "Souza, Carla", "Pátio de sucata", "Piracicaba", "Machado, Victor Alexandre Basilio",
            "70199550", 3, "Acompanhar descarregamento."),
        raw("TASK9000003", "RITM9000003", "Lima, Paulo", "Portaria 2", "Resende", "Mapa, Ana Paula", "x1", 9, "Segurança patrimonial."),
    ]]


def list_tasks() -> list[dict]:
    http, headers = sn_api._client()
    resp = http.get(f"{sn_api.base_url}/api/now/table/sc_task", headers=headers, timeout=30, params={
        "sysparm_query": f"{BOARD_FILTER}^request_item.cat_itemIN{','.join(CAT_ITEMS)}^ORDERBYopened_at",
        "sysparm_fields": FIELDS, "sysparm_display_value": "all", "sysparm_limit": 500})
    _check(resp)
    return resp.json().get("result", [])


def ocultas() -> set[str]:
    try:
        return {n.strip().upper() for n in json.loads(OCULTAS_PATH.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return set()


def get_tasks(force: bool = False) -> dict:
    """KPIs + tarefas de acesso a imagens abertas. Cache curto; erro de sessão sobe como SNAuthError."""
    if not force and _cache["data"] and time.time() - _cache["at"] < CACHE_TTL:
        return _cache["data"]
    now = datetime.now(_TZ)
    if config.SERVICENOW_MOCK:
        rows = _mock_rows(now)
    else:
        rows = [normalize(r, now, session.user) for r in list_tasks()]
    esconder = ocultas()
    rows = [r for r in rows if (r["number"] or "").upper() not in esconder]
    rows.sort(key=lambda r: r["aberto"] or "")
    data = {"atualizado_em": now.isoformat(), "kpis": summarize(rows), "rows": rows,
            "board_url": f"https://{config.SERVICENOW_INSTANCE}.service-now.com/$vtb.do?sysparm_board={BOARD}"}
    _cache.update(at=time.time(), data=data)
    return data

"""RITM de acompanhamento (skill operador-cftv, seção 7).

Rascunho determinístico + checagem de duplicidade. A criação real usa a API do catálogo (order_now) com a sessão do
navegador; o formulário do portal (headless) fica como plano B. Em dry-run/mock só simula.
"""
import json
import re
from functools import lru_cache

from backend import textos
from backend.config import ROOT, config
from backend.payload import build_title, mapa_localidade, field_codes, _codes

CAT_ITEM = "58ce76801b54cdd865717bff034bcb28"
CATALOG_URL = f"https://{config.SERVICENOW_INSTANCE}.service-now.com/sp_iamsmart?id=sc_cat_item&sys_id={CAT_ITEM}"
OPENED_BY = "a37f083f3b5c7a548c9f67dc73e45a50"
PENDENCIAS = ["PEMT", "Infraestrutura", "Elétrica", "Recurso", "Andaime", "Redes", "PTA", "Agendamento"]

_ANALISE = {
    "PEMT": "PEMT",
    "Infraestrutura": "intervenção de infraestrutura",
    "Elétrica": "intervenção elétrica",
    "Recurso": "disponibilização de recurso",
    "Andaime": "montagem de andaime",
    "Redes": "intervenção da equipe de redes",
    "PTA": "PTA",
    "Agendamento": "agendamento de acesso",
}

# RITMs simuladas em mock (memória do processo): permite testar a checagem de duplicidade
_MOCK_RITMS: list[dict] = []


@lru_cache(maxsize=1)
def locais() -> list[dict]:
    """Localidades "CFTV - ..." do formulário (data/ritm_locais.json, gerado por scripts/inspect_ritm_item.py)."""
    try:
        with open(ROOT / "data" / "ritm_locais.json", encoding="utf-8") as f:
            return json.load(f)["locais"]
    except (OSError, ValueError, KeyError):
        return []


def local_id(nome: str) -> str | None:
    return next((x["sys_id"] for x in locais() if x["nome"] == (nome or "").strip()), None)


def render_description(incident_number: str, causa: str, pendencia: str, encaminhamento: str | None,
                       ritm: str | None = None, sla_proximo: bool = False) -> str:
    """Texto da RITM e da work note (manual: pendências externas). Sem número, o Encaminhamento fica com [RITM]."""
    return textos.ritm_descricao(causa, pendencia, encaminhamento, ritm, sla_proximo)


def sla_proximo(due_date: str | None, horas: int = 24) -> bool:
    """SLA (valor bruto do ServiceNow, UTC) vencendo nas próximas `horas`."""
    from datetime import datetime, timezone
    try:
        d = datetime.strptime((due_date or "")[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return (d - datetime.now(timezone.utc)).total_seconds() < horas * 3600


def build_draft(inc: dict) -> dict:
    """Rascunho da RITM (editável na UI). Não inventa ação de campo."""
    loc = inc.get("localidade")
    m = mapa_localidade(loc)
    cidade = m.get("cidade") or loc or ""
    short = inc.get("short_description") or ""
    title, _ = build_title(cidade, short, inc.get("description") or "", bool(loc and "LORA" in loc),
                           inc.get("camera_codigo"))
    causa = re.sub(rf"^{re.escape(cidade)}\s*-\s*", "", title).strip() or short
    cods = field_codes(inc.get("camera_codigo")) or _codes(title) or _codes(short)
    pend = inc.get("pendencia") if inc.get("pendencia") in PENDENCIAS else ""
    warnings = []
    local = m.get("ritm_local") or ""
    if not local:
        warnings.append("Localidade do formulário não mapeada para esta unidade: escolha na lista.")
    if not cods:
        warnings.append("Sem código de câmera: informe a subárea (setor da planta).")
    if not pend:
        warnings.append(f"Escolha a pendência ({', '.join(PENDENCIAS)}).")
    sla = sla_proximo(inc.get("due_date"))
    encam = textos.pendencia(pend)[1]
    return {
        "incident_number": inc["incident_number"],
        "localidade_form": local,
        "locais": [x["nome"] for x in locais()],
        "subarea": " / ".join(cods),
        "pendencia": pend,
        "causa": causa,
        "encaminhamento": encam,
        "sla_proximo": sla,
        "modelos": {k: {"recurso": v[0], "aguardando": v[1]} for k, v in textos.PENDENCIAS.items()},
        "descricao": render_description(inc["incident_number"], causa, pend, encam, sla_proximo=sla),
        "cameras": cods,
        "warnings": warnings,
    }


def _mock_today() -> list[dict]:
    return list(_MOCK_RITMS)


def _variaveis(http, base: str, headers: dict | None, ritm_sys_id: str) -> str:
    o = http.get(f"{base}/api/now/table/sc_item_option_mtom", timeout=20, headers=headers, params={
        "sysparm_query": f"request_item={ritm_sys_id}",
        "sysparm_fields": "sc_item_option.item_option_new.question_text,sc_item_option.value"})
    o.raise_for_status()
    return " ".join((x.get("sc_item_option.value") or "") for x in o.json().get("result", []))


def find_today(http, base: str, headers: dict | None = None) -> list[dict]:
    """RITMs de hoje abertas pelo Victor, com a descrição (variáveis) de cada uma."""
    if config.SERVICENOW_MOCK or http is None:
        return _mock_today()
    q = (f"cat_item={CAT_ITEM}^opened_by={OPENED_BY}^sys_created_onONToday@javascript:gs.beginningOfToday()"
         "@javascript:gs.endOfToday()^ORDERBYDESCsys_created_on")
    r = http.get(f"{base}/api/now/table/sc_req_item", timeout=20, headers=headers, params={
        "sysparm_query": q, "sysparm_limit": 20,
        "sysparm_fields": "number,request.number,sys_id,sys_created_on"})
    r.raise_for_status()
    return [{"number": it["number"], "req": it.get("request.number"), "sys_id": it["sys_id"],
             "texto": _variaveis(http, base, headers, it["sys_id"])} for it in r.json().get("result", [])]


def duplicates(cameras: list[str], incident_number: str, today: list[dict]) -> list[str]:
    """Avisos: RITM de hoje citando o mesmo incidente ou as mesmas câmeras."""
    avisos = []
    for r in today:
        txt = (r.get("texto") or "").upper()
        if incident_number.upper() in txt:
            avisos.append(f"{r['number']} (hoje) já cita {incident_number}.")
            continue
        comuns = [c for c in cameras if c.upper() in txt]
        if comuns:
            avisos.append(f"{r['number']} (hoje) cita as mesmas câmeras: {', '.join(comuns)}.")
    return avisos


# ---------------- criação real (API do catálogo) ----------------
class CatalogoIndisponivel(Exception):
    """A API do catálogo recusou (403/404): usar o formulário do portal."""


def _ref(v):
    return v.get("value") if isinstance(v, dict) else v


def submit_via_catalog(http, base: str, headers: dict, local_sys_id: str, subarea: str, pendencia: str,
                       descricao: str) -> dict:
    """POST order_now do item da RITM. Variáveis com default por script (centro de custo, empresa...) vão explícitas,
    lidas do próprio usuário, para não depender da avaliação no servidor. Devolve {number, req, sys_id, texto}."""
    u = http.get(f"{base}/api/now/table/sys_user/{OPENED_BY}", timeout=20, headers=headers,
                 params={"sysparm_fields": "user_name,email,company,department,cost_center"})
    u.raise_for_status()
    user = u.json().get("result", {})
    variables = {
        "location_00": local_sys_id,
        "subrea_00": subarea,
        "pendncia_00": pendencia,
        "descrio_detalhada_do_problema_00": descricao,
        "opened_by": OPENED_BY,
        "rtedfor": OPENED_BY,
        "usuarioderede": _ref(user.get("user_name")),
        "rf_email": _ref(user.get("email")),
        "company": _ref(user.get("company")),
        "department_department": _ref(user.get("department")),
        "cost_center_cost_center": _ref(user.get("cost_center")),
    }
    r = http.post(f"{base}/api/sn_sc/servicecatalog/items/{CAT_ITEM}/order_now", timeout=60, headers=headers,
                  json={"sysparm_quantity": "1", "variables": {k: v for k, v in variables.items() if v}})
    if r.status_code in (403, 404):
        raise CatalogoIndisponivel(f"order_now {r.status_code}")
    r.raise_for_status()
    res = r.json().get("result", {})
    req_id = res.get("request_id") or res.get("sys_id")
    req_num = res.get("request_number") or res.get("number")
    it = http.get(f"{base}/api/now/table/sc_req_item", timeout=20, headers=headers, params={
        "sysparm_query": f"request={req_id}", "sysparm_fields": "number,sys_id", "sysparm_limit": 1})
    it.raise_for_status()
    rows = it.json().get("result", [])
    if not rows:
        return {"number": None, "req": req_num, "sys_id": None, "texto": ""}
    texto = _variaveis(http, base, headers, rows[0]["sys_id"])
    return {"number": rows[0]["number"], "req": req_num, "sys_id": rows[0]["sys_id"], "texto": texto}


# ---------------- plano B: formulário do portal ----------------
_JS = r"""
async (P) => {
  await new Promise(r => setTimeout(r, 4000));
  const s2 = jQuery('#sp_formfield_location_00').data('select2');
  const res = await new Promise(ok => { s2.opts.query.call(s2, {term: 'CFTV', page: 1, context: null, callback: ok}); setTimeout(() => ok(null), 6000); });
  const alvo = res && res.results.find(x => x.name === P.local);
  if (!alvo) return JSON.stringify({erro: 'localidade não encontrada', opcoes: res && res.results.map(x => x.name)});
  s2.onSelect(alvo); try { jQuery('#sp_formfield_location_00').select2('close'); } catch (e) {}
  let gf = null, s = angular.element(document.getElementById('sp_formfield_subrea_00')).scope();
  while (s && !gf) { if (typeof s.getGlideForm === 'function') gf = s.getGlideForm(); s = s.$parent; }
  gf.setValue('subrea_00', P.subarea); gf.setValue('pendncia_00', P.pendencia); gf.setValue('descrio_detalhada_do_problema_00', P.desc);
  return JSON.stringify([gf.getDisplayValue('location_00'), gf.getValue('subrea_00'), gf.getValue('pendncia_00'), gf.getValue('descrio_detalhada_do_problema_00').length]);
}
"""


def submit_via_portal(local: str, subarea: str, pendencia: str, descricao: str) -> dict:
    """Preenche e envia o formulário no portal (headless, perfil salvo). Só se o catálogo recusar. NÃO TESTADO."""
    from playwright.sync_api import sync_playwright
    from backend.sn_session import PROFILE_DIR

    with sync_playwright() as p:
        ctx = None
        for channel in ("msedge", "chrome", None):
            try:
                ctx = p.chromium.launch_persistent_context(
                    str(PROFILE_DIR), headless=True, **({"channel": channel} if channel else {}))
                break
            except Exception:
                continue
        if ctx is None:
            return {"ok": False, "erro": "Nenhum navegador disponível."}
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(CATALOG_URL, wait_until="domcontentloaded", timeout=60000)
            filled = json.loads(page.evaluate(_JS, {"local": local, "subarea": subarea, "pendencia": pendencia, "desc": descricao}))
            if isinstance(filled, dict):
                return {"ok": False, "erro": filled.get("erro"), "opcoes": filled.get("opcoes")}
            if not (filled[0] == local and filled[1] == subarea and filled[2] == pendencia and filled[3] == len(descricao)):
                return {"ok": False, "erro": f"Formulário não bateu com o esperado: {filled}"}
            page.evaluate("document.getElementById('submit-btn').click()")
            page.wait_for_timeout(10000)
            return {"ok": page.title().lower().startswith("solicita"), "titulo": page.title()}
        finally:
            ctx.close()


def latest_after(http, base: str, before: set[str], headers: dict | None = None) -> dict | None:
    """RITM mais recente de hoje que não estava em `before` (números)."""
    for r in find_today(http, base, headers):
        if r["number"] not in before:
            return r
    return None

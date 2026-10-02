import time
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from backend.models import IncidentIn, ApproveIn, RitmIn, TeamsDraftIn, ControleIn
from backend.rules_engine import engine
from backend.servicenow_api import sn_api, SNAuthError
from backend.analysis import analyze
from backend.claude_caller import call_claude_for_localidade, call_claude_for_ritm
from backend.config import config
from backend import scom, servidores, teams, controle, ritm as ritm_mod, a4
from backend.sn_session import session
from backend.payload import build_first_touch, already_in_progress, display_title
from backend import db, fluxo
from backend.payload import ASSIGNED_TO

router = APIRouter(prefix="/incidents", tags=["incidents"])

@router.post("")
def process_incident(incident: IncidentIn):
    """Buscar no ServiceNow, aplicar regras (LLM só se confiança baixa) e salvar sugestão"""
    try:
        sn_incident = sn_api.get_incident(incident.incident_number)
        lote = sn_api.estado_lote([sn_incident["sys_id"]]) if sn_incident and sn_incident.get("sys_id") else []
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar no cabeçalho")
    if not sn_incident:
        raise HTTPException(status_code=404, detail="Incidente não encontrado no ServiceNow")
    n = incident.incident_number.upper()
    atual = (db.get_incident(n) or {}).get("status")
    res = analyze(n, sn_incident)
    if lote:  # incidente fora da Entrada (outro estado, outra fila, nota minha) não volta para ela
        sn = lote[0]
        status = fluxo.classificar(sn, atual, sn_api.meu_nome())
        if status != fluxo.ENTRADA:
            db.set_fluxo(n, status, sn["state"], sn["grupo_nome"], (fluxo.autores(sn["work_notes"]) or [None])[0])
            res["aviso"] = ("Já encerrado no ServiceNow." if status == fluxo.ENCERRADO else
                            f"Já tratado no ServiceNow ({sn['grupo_nome'] or 'sem fila'}): vai para a Saída, sem despacho.")
    res["status"] = db.get_incident(n)["status"]
    return res

def _reread(n: str) -> dict:
    """Relê no ServiceNow (incidente + Número do Objeto) e reaplica as regras. Só pendentes; sem LLM; status mantido."""
    inc = db.get_incident(n)
    if not inc:
        raise HTTPException(status_code=404, detail="Incidente não analisado; processe primeiro")
    if inc.get("status") != "analisado":
        raise HTTPException(status_code=409, detail="Já despachado: nada a reler")
    sn_incident = sn_api.get_incident(n)
    if not sn_incident:
        raise HTTPException(status_code=404, detail="Incidente não encontrado no ServiceNow")
    analyze(n, sn_incident, allow_llm=False)
    novo = db.get_incident(n)
    antes, depois = display_title(inc)["titulo_padrao"], display_title(novo)["titulo_padrao"]
    return {"incident_number": n, "camera_codigo": novo.get("camera_codigo"), "localidade": novo.get("localidade"),
            "titulo_padrao": depois, "mudou": antes != depois or inc.get("camera_codigo") != novo.get("camera_codigo")}

@router.post("/refresh-pendentes")
def refresh_pendentes():
    """Confere a Entrada no ServiceNow (o que já saiu vai para a Saída) e relê os que continuam. Somente leitura."""
    out, erros = [], []
    try:
        rec = fluxo.reconciliar()
        for i in db.list_incidents(200, only_pending=True):
            try:
                out.append(_reread(i["incident_number"]))
            except HTTPException as e:
                erros.append(f"{i['incident_number']}: {e.detail}")
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar no cabeçalho")
    return {"relidos": len(out), "mudaram": [r for r in out if r["mudou"]], "erros": erros,
            "sairam": [m for m in rec["mudaram"] if m[1] == fluxo.ENTRADA]}

@router.post("/{incident_number}/refresh")
def refresh_incident(incident_number: str):
    try:
        return _reread(incident_number.upper())
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar no cabeçalho")

def _camera_testada(n: str) -> dict | None:
    """Último teste de câmera com snapshot OK e print anexado depois dele (histórico local). Senão None."""
    snaps = db.list_history(20, n, "snapshot")
    if not snaps:
        return None
    ult = snaps[0]
    codigos = [p.split(":")[0].strip() for p in (ult["resultado"] or "").split(";") if p.strip().endswith(": ok")]
    anexos = [h for h in db.list_history(20, n, "snapshot_anexo") if h["id"] > ult["id"] and "anexado" in (h["resultado"] or "")]
    if not codigos or not anexos:
        return None
    quando = datetime.strptime(str(ult["created_at"])[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return {"codigos": codigos, "hora": quando.astimezone(scom.BRT).strftime("%H:%M")}


def _contexto(inc: dict) -> dict:
    """Testes feitos antes do despacho que mudam a work note (validação SCOM, câmera testada)."""
    n = inc["incident_number"]
    return {"scom": scom.ultima_validacao(n), "camera": _camera_testada(n)}


def _prepare(incident_number: str, overrides: ApproveIn | None):
    inc = db.get_incident(incident_number.upper())
    if not inc:
        raise HTTPException(status_code=404, detail="Incidente não analisado; processe primeiro")
    if not inc.get("sys_id"):
        raise HTTPException(status_code=409, detail="sys_id ausente; reprocesse o incidente")

    changes = {k: v for k, v in (overrides.model_dump() if overrides else {}).items() if v is not None}
    editado = any(inc.get(k) != v for k, v in changes.items())
    final = {**inc, **changes}
    if not final.get("grupo"):
        raise HTTPException(status_code=422, detail="Sem grupo de atribuição definido")

    try:
        current = sn_api.get_current(inc["sys_id"])
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar")
    if current is None:  # sem o estado atual não dá para garantir a checagem de duplicidade
        raise HTTPException(status_code=502, detail="Não consegui ler o estado atual do incidente; nada foi enviado")
    if already_in_progress(current):
        raise HTTPException(status_code=409, detail="Já está Em Andamento com work note; não mexer (só reportar)")
    ctx = _contexto(inc)
    fields, warnings = build_first_touch(inc, final, current, ctx)
    val = ctx["scom"]
    nota_scom = val and (fields.get("work_notes") or "").startswith(scom.WORK_NOTE.format(host=val["host"]))
    return inc, changes, editado, fields, warnings, (val["arquivo"] if nota_scom else None)

@router.get("/{incident_number}/payload")
def preview_payload(incident_number: str):
    """Mostra o PATCH que seria enviado (sem enviar)"""
    _, _, _, fields, warnings, anexo = _prepare(incident_number, None)
    return {"fields": fields, "warnings": warnings, "anexo": anexo.name if anexo else None,
            "dry_run": config.SERVICENOW_DRY_RUN or config.SERVICENOW_MOCK}

@router.post("/{incident_number}/approve")
def approve_incident(incident_number: str, overrides: ApproveIn | None = None):
    """Aplica a primeira tratativa (sugestão ou versão editada) no ServiceNow"""
    start = time.perf_counter()
    inc, changes, editado, fields, warnings, anexo = _prepare(incident_number, overrides)
    anexado = _anexar_ping(inc, anexo) if anexo else None  # a nota diz "evidência anexada": anexo antes do PATCH
    if not sn_api.patch_incident(inc["sys_id"], fields):
        raise HTTPException(status_code=502, detail="Falha ao atualizar o ServiceNow")

    db.set_incident_status(incident_number.upper(), "aprovado", changes if editado else None)
    elapsed_ms = (time.perf_counter() - start) * 1000
    db.add_history(incident_number.upper(), "editado" if editado else "aprovado",
                   f"dry_run={config.SERVICENOW_DRY_RUN} grupo={fields['assignment_group']} "
                   f"titulo={fields.get('short_description', '(mantido)')}", False, elapsed_ms)
    return {"ok": True, "editado": editado, "dry_run": config.SERVICENOW_DRY_RUN or config.SERVICENOW_MOCK,
            "fields": fields, "warnings": warnings, "anexo": anexado, "tempo_ms": round(elapsed_ms, 1)}

def _anexar_ping(inc: dict, arquivo: Path) -> str:
    """Anexa a imagem do ping ao incidente sem duplicar. Falha = 502 e nada mais é enviado. Respeita o dry-run."""
    try:
        existentes = sn_api.list_attachment_names(inc["sys_id"])
        if existentes is None:
            raise HTTPException(status_code=502, detail="Não consegui listar os anexos; nada foi enviado")
        if arquivo.name in existentes:
            status = "já anexado"
        elif sn_api.attach_file(inc["sys_id"], arquivo.name, arquivo.read_bytes(), "image/png"):
            status = "anexado"
        else:
            raise HTTPException(status_code=502, detail="Falha ao anexar a evidência do ping; nada foi enviado")
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar")
    db.add_history(inc["incident_number"], "ping_anexo",
                   f"dry_run={config.SERVICENOW_DRY_RUN or config.SERVICENOW_MOCK} {arquivo.name}={status}", False, 0)
    return status

@router.get("/{incident_number}/ping/evidencia")
def ping_evidencia(incident_number: str):
    """Imagem do último ping OK do incidente (ainda válida)."""
    val = scom.ultima_validacao(incident_number.upper())
    if not val:
        raise HTTPException(status_code=404, detail="Sem validação de ping recente")
    return FileResponse(val["arquivo"], media_type="image/png", headers={"Cache-Control": "no-store"})

@router.post("/{incident_number}/ping/registrar")
def ping_registrar(incident_number: str):
    """SCOM já despachado: anexa a imagem do ping e posta a work note de validação. Não muda estado, não repete."""
    inc = _get_inc(incident_number)
    n = inc["incident_number"]
    if not scom.is_scom_alert(inc.get("short_description") or "", inc.get("description") or ""):
        raise HTTPException(status_code=422, detail="Não é um alerta SCOM")
    val = scom.ultima_validacao(n)
    if not val:
        raise HTTPException(status_code=409, detail=f"Sem ping OK nos últimos {scom.VALIDADE_MIN} min: teste de novo")
    if not inc.get("sys_id"):
        raise HTTPException(status_code=409, detail="sys_id ausente")
    nota = scom.WORK_NOTE.format(host=val["host"])
    try:
        atual = sn_api.get_current(inc["sys_id"])
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar")
    if atual is None:
        raise HTTPException(status_code=502, detail="Não consegui ler o incidente; nada foi enviado")
    anexo = _anexar_ping(inc, val["arquivo"])
    dry = config.SERVICENOW_DRY_RUN or config.SERVICENOW_MOCK
    if nota.splitlines()[0].lower() in (atual.get("work_notes") or "").lower():
        return {"status": "já registrada", "anexo": anexo, "dry_run": dry}
    if not sn_api.patch_incident(inc["sys_id"], {"work_notes": nota}):
        raise HTTPException(status_code=502, detail="Falha ao gravar a work note no ServiceNow")
    db.add_history(n, "nota_validacao", f"dry_run={dry} {val['host']}", False, 0)
    return {"status": "registrada", "anexo": anexo, "work_note": nota, "dry_run": dry}

class PingIn(BaseModel):
    host: str | None = None


def _detect_host(inc: dict) -> dict:
    """Host do incidente: alerta SCOM, depois servidor citado no texto (lista ou padrão de hostname)."""
    short, desc = inc.get("short_description") or "", inc.get("description") or ""
    is_scom = scom.is_scom_alert(short, desc)
    host = scom.extract_host(short, desc) if is_scom else None
    ficha = servidores.find(host) if host else None
    if not host:
        ficha = servidores.detect(short, desc)
        host = ficha["nome"] if ficha else None
    return {"host": host, "ip": (ficha or {}).get("ip"), "ficha": ficha, "scom": is_scom}

@router.get("/{incident_number}/host")
def incident_host(incident_number: str):
    """Servidor detectado no incidente (para o painel de ping). Somente leitura."""
    inc = db.get_incident(incident_number.upper())
    if not inc:
        raise HTTPException(status_code=404, detail="Incidente não analisado; processe primeiro")
    return _detect_host(inc)

@router.post("/{incident_number}/ping")
def ping_incident(incident_number: str, body: PingIn | None = None, evidence: bool = True):
    """Ping de um servidor do incidente (detectado ou informado), a partir desta máquina (precisa de VPN).
    Só o alerta SCOM devolve texto de encerramento. Não escreve no ServiceNow."""
    inc = db.get_incident(incident_number.upper())
    if not inc:
        raise HTTPException(status_code=404, detail="Incidente não analisado; processe primeiro")
    det = _detect_host(inc)
    typed = (body.host or "").strip() if body else ""
    if typed:
        ficha = servidores.find(typed)
        host, ip, is_scom = (ficha["nome"] if ficha else typed), (ficha or {}).get("ip"), det["scom"] and det["host"] == typed.upper()
    else:
        host, ip, is_scom = det["host"], det["ip"], det["scom"]
    if not host:
        raise HTTPException(status_code=422, detail="Nenhum servidor identificado no incidente; informe o host")
    try:
        if is_scom:
            res = scom.check(inc.get("short_description") or "", inc.get("description") or "", evidence=evidence,
                             incident=inc["incident_number"])
        else:
            res = scom.ping_host(host, ip=ip, evidence=evidence, incident=inc["incident_number"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    res["scom"] = is_scom
    res["ficha"] = servidores.find(host)
    db.add_history(incident_number.upper(), "ping",
                   f"host={host} ok={res.get('ok')} perda={res.get('ping', {}).get('perda_percentual')}"
                   + (f" evid={res['evidencia']}" if is_scom and res.get("evidencia") else ""), False, 0)
    return res

def _get_inc(n: str) -> dict:
    """Incidente da fila local ou, se nunca passou por aqui (já Em Andamento), lido do ServiceNow."""
    inc = db.get_incident(n.upper())
    if inc:
        return inc
    from backend.routes.camera import _resolve
    info = _resolve(n)
    return {"incident_number": info["incident_number"], "sys_id": info["sys_id"], "short_description": info["titulo"],
            "description": info["descricao"], "localidade": info["localidade"], "camera_codigo": info["camera_codigo"],
            "pendencia": None}

def _today_ritms():
    http = session.http()
    try:
        return ritm_mod.find_today(http, sn_api.base_url, session.headers() if http else None)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Não consegui consultar as RITMs de hoje: {e}")

@router.get("/{incident_number}/ritm/draft")
def ritm_draft(incident_number: str):
    """Rascunho da RITM + avisos de duplicidade. Não cria nada."""
    inc = _get_inc(incident_number)
    draft = ritm_mod.build_draft(inc)
    draft["duplicidade"] = ritm_mod.duplicates(draft["cameras"], inc["incident_number"], _today_ritms())
    draft["ja_criada"] = [h["resultado"] for h in db.list_history(50, inc["incident_number"], "ritm")]
    draft["pendencias"] = ritm_mod.PENDENCIAS
    draft["dry_run"] = config.SERVICENOW_DRY_RUN or config.SERVICENOW_MOCK
    return draft

@router.post("/{incident_number}/ritm")
def create_ritm(incident_number: str, body: RitmIn):
    """RITM → work note no incidente. (Teams e planilha: passo 5.) Em dry-run/mock simula."""
    start = time.perf_counter()
    inc = _get_inc(incident_number)
    n = inc["incident_number"]
    if db.list_history(50, n, "ritm"):
        raise HTTPException(status_code=409, detail="Já existe RITM registrada para este incidente")
    if body.pendencia not in ritm_mod.PENDENCIAS:
        raise HTTPException(status_code=422, detail=f"Pendência inválida ({', '.join(ritm_mod.PENDENCIAS)})")
    today = _today_ritms()
    cams = list(dict.fromkeys(ritm_mod.field_codes(body.subarea) + ritm_mod._codes(f"{body.subarea} {body.descricao}")))
    dup = ritm_mod.duplicates(cams, n, today)
    if dup and not body.force:
        raise HTTPException(status_code=409, detail="Possível duplicidade: " + " ".join(dup))

    simulado = config.SERVICENOW_DRY_RUN or config.SERVICENOW_MOCK
    if simulado:
        numero = f"RITM{9000001 + len(ritm_mod._MOCK_RITMS)}" if config.SERVICENOW_MOCK else "RITM(simulada)"
        req = "REQ(simulada)"
        if config.SERVICENOW_MOCK:
            req = f"REQ{9000001 + len(ritm_mod._MOCK_RITMS)}"
            ritm_mod._MOCK_RITMS.append({"number": numero, "req": req, "sys_id": f"mock-{numero.lower()}",
                                         "texto": f"{body.subarea} {body.descricao}"})
    else:
        if not session.connected:
            raise HTTPException(status_code=409, detail="ServiceNow desconectado: use Conectar")
        local_id = ritm_mod.local_id(body.localidade_form)
        if not local_id:
            raise HTTPException(status_code=422, detail=f"Localidade do formulário desconhecida: {body.localidade_form}")
        http, headers = session.http(), session.headers()
        try:
            novo = ritm_mod.submit_via_catalog(http, sn_api.base_url, headers, local_id, body.subarea,
                                               body.pendencia, body.descricao)
        except ritm_mod.CatalogoIndisponivel:
            r = ritm_mod.submit_via_portal(body.localidade_form, body.subarea, body.pendencia, body.descricao)
            if not r.get("ok"):
                raise HTTPException(status_code=502, detail=f"Envio não confirmado: {r.get('erro') or r.get('titulo')}. "
                                                            "Confira no portal antes de tentar de novo.")
            novo = ritm_mod.latest_after(http, sn_api.base_url, {t["number"] for t in today}, headers)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Falha ao enviar pelo catálogo: {e}. "
                                                        "Confira no portal se a RITM saiu antes de tentar de novo.")
        if not novo or not novo.get("number"):
            raise HTTPException(status_code=502, detail="Enviado, mas não achei a RITM nova; confira no portal (não reenviar).")
        numero, req = novo["number"], novo.get("req") or ""

    nota = body.descricao.replace("requisição.", f"requisição {numero}.")
    current = sn_api.get_current(inc["sys_id"]) if inc.get("sys_id") else None
    nota_dup = bool(current and numero in (current.get("work_notes") or ""))
    if inc.get("sys_id") and not nota_dup:
        if not sn_api.patch_incident(inc["sys_id"], {"work_notes": nota}):
            raise HTTPException(status_code=502, detail=f"{numero} criada, mas a work note falhou: poste manualmente.")
    db.add_history(n, "ritm", numero, False, (time.perf_counter() - start) * 1000)
    return {"ok": True, "ritm": numero, "req": req, "simulado": simulado, "work_note": nota,
            "work_note_ja_existia": nota_dup, "duplicidade_ignorada": dup}

@router.post("/{incident_number}/teams-draft")
def teams_draft(incident_number: str, body: TeamsDraftIn):
    """Mensagem ao solicitante + link do Teams. NUNCA envia; `abrir` só pré-preenche o chat."""
    inc = _get_inc(incident_number)
    caller = sn_api.get_caller(inc["sys_id"]) if inc.get("sys_id") else None
    if not caller or not caller.get("email") or not caller.get("nome"):
        raise HTTPException(status_code=502, detail="Não consegui ler nome/e-mail do solicitante no ServiceNow")
    if body.modelo == "acesso":
        msg = teams.build_message_acesso(inc["incident_number"], teams.primeiro_nome(caller["nome"]))
    else:
        if not body.ritm.strip():
            raise HTTPException(status_code=422, detail="Informe a RITM")
        d = ritm_mod.build_draft(inc)
        ident = body.identificado or teams.default_identificado(d["causa"], body.pendencia)
        msg = teams.build_message(inc["incident_number"], teams.primeiro_nome(caller["nome"]), ident, body.ritm,
                                  len(d["cameras"]))
    url = teams.build_url(caller["email"], msg)
    if body.abrir:
        teams.open_draft(url)
    return {"mensagem": msg, "email": caller["email"], "solicitante": caller["nome"], "url": url,
            "aberto": body.abrir, "aviso": "Rascunho: revise o espaçamento e envie você mesmo."}

@router.post("/{incident_number}/controle")
def controle_row(incident_number: str, body: ControleIn):
    """Lança a RITM na planilha de controle. Em dry-run/mock só mostra a linha (não grava)."""
    inc = _get_inc(incident_number)
    d = ritm_mod.build_draft(inc)
    unidade = inc.get("localidade") or ""
    texto = f"{inc.get('short_description') or ''} {inc.get('description') or ''} {body.subarea}"
    try:
        row = controle.build_row(inc["incident_number"], body.req, body.ritm, unidade,
                                 body.resumo or controle.default_resumo(d["causa"], body.pendencia),
                                 body.pendencia, controle.is_metalicos(texto))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    apply = not (config.SERVICENOW_DRY_RUN or config.SERVICENOW_MOCK)
    try:
        res = controle.append_row(row, apply=apply)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Planilha não encontrada: {config.CONTROLE_XLSX}")
    if res.get("duplicada"):
        raise HTTPException(status_code=409, detail=res["erro"])
    if not res["ok"]:
        raise HTTPException(status_code=423, detail=res["erro"])
    db.add_history(inc["incident_number"], "controle", f"{body.ritm} linha {res['linha']} gravado={res['gravado']}", False, 0)
    return {**res, "simulado": not apply}

def _sla_brt(due: str | None) -> str:
    """'2026-10-05 21:00:00' (UTC, valor bruto do ServiceNow) -> '05/10/2026 18:00' (Brasília)."""
    try:
        d = datetime.strptime(due or "", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return due or ""
    return d.astimezone(scom.BRT).strftime("%d/%m/%Y %H:%M")


def _email_a4(incident_number: str) -> tuple[dict, dict]:
    inc = _get_inc(incident_number)
    disp = display_title(inc)
    if not disp.get("a4"):
        raise HTTPException(status_code=409, detail="Incidente não é A4")
    try:
        sn_incident = sn_api.get_incident(inc["incident_number"])
        caller = sn_api.get_caller(inc.get("sys_id")) if inc.get("sys_id") else None
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar no cabeçalho")
    if not sn_incident:
        raise HTTPException(status_code=404, detail="Incidente não encontrado no ServiceNow")
    caller = caller or {}
    mail = a4.email_a4(inc["incident_number"], inc.get("localidade") or "",
                       disp.get("descricao_util") or inc.get("short_description") or "",
                       caller.get("nome") or inc.get("caller_id") or "", caller.get("email") or "",
                       _sla_brt(sn_incident.get("due_date")))
    return inc, mail


@router.get("/{incident_number}/email-a4/preview")
def email_a4_preview(incident_number: str):
    """Prévia do e-mail A4 (para, cc, assunto, corpo, mailto). Só leitura; não abre nada."""
    return _email_a4(incident_number)[1]


@router.post("/{incident_number}/email-a4")
def email_a4_draft(incident_number: str):
    """Registra que o rascunho A4 foi aberto e devolve o mailto: o painel abre o app de e-mail padrão (Outlook clássico
    ou novo) com tudo preenchido. Nada é enviado pelo agente."""
    inc, mail = _email_a4(incident_number)
    anteriores = db.list_history(5, inc["incident_number"], "email_a4")
    db.add_history(inc["incident_number"], "email_a4", f"Rascunho aberto: {mail['assunto']}")
    return {**mail, "sucesso": True, "ja_aberto_antes": len(anteriores)}

CLOSE_CODE = "Solved"


@router.post("/{incident_number}/close")
def close_incident(incident_number: str, body: dict):
    """Encerra (Resolvido, fluxo 9.3 da skill): state 6, close_code, close_notes e work note. Só incidente da Saída
    (já despachado/tratado); respeita dry-run. Pedido explícito do Victor = gesto de segurar no painel."""
    inc = _get_inc(incident_number)
    n = inc["incident_number"]
    texto = (body.get("work_notes") or "").strip()
    if not texto:
        raise HTTPException(status_code=422, detail="Escreva a nota de encerramento")
    if inc.get("status") == fluxo.ENCERRADO:
        raise HTTPException(status_code=409, detail="Já encerrado")
    if inc.get("status") not in fluxo.SAIDA:
        raise HTTPException(status_code=409, detail="Ainda na Entrada: despache antes de encerrar")
    if not inc.get("sys_id"):
        raise HTTPException(status_code=409, detail="sys_id ausente; reprocesse o incidente")
    payload = {"state": "6", "close_code": CLOSE_CODE, "close_notes": texto, "work_notes": texto,
               "u_is_recurring_incident": "no", "assigned_to": ASSIGNED_TO}
    simulado = config.SERVICENOW_DRY_RUN or config.SERVICENOW_MOCK
    try:
        if not sn_api.patch_incident(inc["sys_id"], payload):
            raise HTTPException(status_code=502, detail="ServiceNow recusou o encerramento; nada mudou aqui")
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar no cabeçalho")
    if not simulado:
        db.set_fluxo(n, fluxo.ENCERRADO, "6", inc.get("sn_grupo") or "", inc.get("nota_autor"))
    db.add_history(n, "encerrado", f"dry_run={simulado} state=6 close_code={CLOSE_CODE} nota={texto[:100]}")
    return {"sucesso": True, "simulado": simulado, "fields": payload,
            "mensagem": "Simulado (dry-run): nada enviado" if simulado else "Resolvido no ServiceNow"}

@router.get("")
def list_incidents(limit: int = 50):
    """Entrada: incidentes aguardando primeira tratativa. Só o banco (a reconciliação roda no ciclo do sync)."""
    return [{**i, **display_title(i)} for i in db.list_incidents(limit, only_pending=True)]

@router.get("/saida")
def list_saida(horas: int = 24):
    """Saída: despachados pelo agente e tratados fora dele nas últimas `horas`."""
    return [{**i, **display_title(i)} for i in db.list_saida(max(1, min(horas, 168)))]

@router.get("/{incident_number}")
def get_incident(incident_number: str):
    inc = db.get_incident(incident_number.upper())
    if not inc:
        raise HTTPException(status_code=404, detail="Incidente não encontrado")
    return {**inc, **display_title(inc)}

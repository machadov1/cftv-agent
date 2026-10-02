"""Teste de câmera via Digifort: localizar a câmera pelo 'Número do Objeto', ver se voltou, tirar snapshot, anexar e
registrar a work note de encerramento. Funciona com incidente da fila local ou qualquer incidente já em andamento
(lido do ServiceNow). Nunca muda estado nem encerra o incidente."""
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend import db, digifort, servidores, textos
from backend.config import config, ROOT
from backend.payload import camera_codes
from backend.rules_engine import engine
from backend.servicenow_api import sn_api, SNAuthError

router = APIRouter(tags=["camera"])
EVID = ROOT / "data" / "evidencias"
MAX_CAMERAS = 12


class EscolhaIn(BaseModel):
    consulta: str  # o código/texto do incidente ao qual a escolha responde
    ip: str
    nome: str


class CameraIn(BaseModel):
    localidade: str | None = None  # quando não dá para descobrir sozinho (ou para corrigir)
    escolha: EscolhaIn | None = None  # candidata escolhida por você: testa essa e lembra para as próximas vezes


class NotaIn(BaseModel):
    texto: str
    validacao: str | None = None  # 'Nome Sobrenome' -> 'Validação: Sobrenome, Nome.' no Encerramento


def _safe(s: str) -> str:
    return re.sub(r"[^\w.\-]", "_", s)


def _file(inc_number: str, code: str):
    return EVID / f"snapshot_{_safe(inc_number)}_{_safe(code)}.jpg"


def _localidade_do_grupo(grupo: str | None) -> str | None:
    g = (grupo or "").strip().lower()
    if not g:
        return None
    for r in engine.rules:
        if r.get("localidade") and (r.get("grupo_display") or "").lower() == g:
            return r["localidade"]
    return None


def _resolve(n: str, localidade: str | None = None) -> dict:
    """Dados mínimos do incidente: da fila local, ou do ServiceNow se já está em andamento e nunca passou por aqui."""
    n = n.upper()
    inc = db.get_incident(n)
    if inc:
        short, desc, cam = inc.get("short_description") or "", inc.get("description") or "", inc.get("camera_codigo")
        uloc, sys_id, estado, grupo = inc.get("u_incident_location"), inc["sys_id"], inc.get("status"), inc.get("grupo_display")
    else:
        try:
            sn = sn_api.get_incident(n)
            if not sn:
                raise HTTPException(status_code=404, detail="Incidente não encontrado no ServiceNow")
            short, desc = sn.get("short_description") or "", sn.get("description") or ""
            cam = sn_api.get_camera_code(sn.get("sys_id"))
        except SNAuthError:
            raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar")
        sys_id, estado, grupo, uloc = sn.get("sys_id"), sn.get("state"), sn.get("assignment_group"), sn.get("u_incident_location")
    codes = camera_codes(cam, short, desc)
    consulta = None
    if not codes:  # texto livre ("câmera da portaria"): vale a câmera que você já confirmou para ele
        consulta = (cam or "").strip() or short.strip() or None
        known = digifort.lembrada(consulta) if consulta else None
        if known:
            codes = [known["nome"]]
    # localidade: a informada > a salva > o campo do ServiceNow / regras (inclui prefixo aprendido) > grupo atual
    achada = localidade or (inc or {}).get("localidade")
    if not achada:
        achada = engine.apply_rules({"short_description": short, "description": desc, "u_incident_location": uloc or "",
                                     "camera_codigo": cam or ""})["localidade"] or _localidade_do_grupo(grupo)
    return {"incident_number": n, "sys_id": sys_id, "titulo": short, "descricao": desc, "estado": estado, "grupo": grupo,
            "localidade": achada, "codes": codes[:MAX_CAMERAS], "consulta": consulta, "camera_codigo": cam,
            "local": bool(inc)}


def _pronto(info: dict) -> None:
    if not digifort.configured():
        raise HTTPException(status_code=409, detail="Digifort não configurado: defina DIGIFORT_USER e DIGIFORT_PASSWORD no .env")
    if not info["codes"] and not info["consulta"]:
        raise HTTPException(status_code=422, detail="Incidente sem código nem descrição de câmera para procurar")


@router.get("/digifort/status")
def digifort_status():
    return {"configurado": digifort.configured(), "porta": config.DIGIFORT_PORT, "servidores": servidores.status()}


@router.get("/digifort/teste")
def digifort_teste(ip: str):
    """Teste de conexão/credencial num servidor (versão da API). Somente leitura."""
    if not re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", ip):
        raise HTTPException(status_code=422, detail="Informe um IP")
    try:
        return digifort.version(ip)
    except digifort.DigifortError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/incidents/{incident_number}/camera/check")
def camera_check(incident_number: str, body: CameraIn | None = None):
    """Para cada câmera do incidente: acha o servidor da unidade, confere se voltou e, se sim, guarda um snapshot.
    Não escreve no ServiceNow. Retorna logs de debug."""
    digifort.clear_debug_log()
    info = _resolve(incident_number, body.localidade if body else None)
    _pronto(info)
    if not info["localidade"]:
        raise HTTPException(status_code=422, detail="Não descobri a unidade deste incidente: escolha a localidade para procurar a câmera")
    srv = servidores.cftv_da_unidade(info["localidade"])
    if not srv:
        raise HTTPException(status_code=422, detail=f"Nenhum servidor CFTV de '{info['localidade']}' na lista de servidores")

    escolha = body.escolha if body else None
    if escolha and not any(s["ip"] == escolha.ip for s in srv):
        raise HTTPException(status_code=422, detail="A câmera escolhida não é de um servidor desta unidade")

    EVID.mkdir(parents=True, exist_ok=True)
    cameras = []
    livre = not info["codes"]  # só texto livre: procura pelas palavras, nunca escolhe sozinho
    for code in info["codes"] or [info["consulta"]]:
        item = {"codigo": code, "achada": None, "working": None, "active": None, "inactive_s": None,
                "snapshot": False, "erro": None, "texto_livre": livre}
        if escolha and digifort._fold(escolha.consulta) == digifort._fold(code):
            s = next(s for s in srv if s["ip"] == escolha.ip)
            loc = {"achada": {"servidor": s["nome"], "ip": s["ip"], "nome": escolha.nome}, "candidatas": [], "erros": [],
                   "tentados": [s["nome"]]}
            digifort.lembrar(code, loc["achada"])
            if livre:  # dali em diante o incidente usa o nome real da câmera (arquivo do print, nota de encerramento)
                code = item["codigo"] = escolha.nome
                item["texto_livre"] = False
        else:
            loc = digifort.locate(code, srv, automatico=not livre)
        item.update(tentados=loc["tentados"], candidatas=loc["candidatas"], erros_servidores=loc["erros"])
        if not loc["achada"]:
            ok, falhas = len(loc["tentados"]) - len(loc["erros"]), len(loc["erros"])
            if loc["candidatas"]:
                item["erro"] = ("Nome exato não encontrado: escolha a câmera certa entre as candidatas" if not livre else
                                "Descrição sem código: escolha a câmera entre as candidatas")
            elif ok == 0:
                item["erro"] = "Nenhum servidor da unidade respondeu (VPN, porta ou credencial)"
            elif falhas:
                item["erro"] = (f"Não está nos {ok} servidor(es) que responderam; {falhas} não responderam ou recusaram a "
                                "credencial, e ela pode estar num deles")
            else:
                item["erro"] = "Câmera não encontrada nos servidores da unidade"
            cameras.append(item)
            continue
        cam = loc["achada"]
        item["achada"] = cam
        try:
            item.update(digifort.camera_state(cam["ip"], cam["nome"]))
            if item["active"] is False:
                item["erro"] = "Câmera DESATIVADA no cadastro do Digifort (não é queda de rede): ative ou confira com quem administra o servidor; snapshot não gerado"
            elif item["working"] is False:
                item["erro"] = "Câmera ainda sem sinal no Digifort; snapshot não gerado"
            else:
                _file(info["incident_number"], code).write_bytes(digifort.snapshot(cam["ip"], cam["nome"]))
                item["snapshot"] = True
        except digifort.DigifortError as e:
            item["erro"] = str(e)
        cameras.append(item)

    db.add_history(info["incident_number"], "snapshot",
                   "; ".join(f"{c['codigo']}: " + ("ok" if c["snapshot"] else c["erro"] or "?") for c in cameras), False, 0)
    return {"incidente": {k: info[k] for k in ("incident_number", "titulo", "estado", "grupo", "localidade")},
            "cameras": cameras, "dry_run": config.SERVICENOW_DRY_RUN or config.SERVICENOW_MOCK,
            "debug": digifort.get_debug_log()}


@router.get("/incidents/{incident_number}/camera/snapshot/{code}")
def camera_snapshot(incident_number: str, code: str):
    path = _file(incident_number.upper(), code)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Snapshot ainda não gerado")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


def _arquivos(info: dict):
    return [(c, p) for c, p in ((c, _file(info["incident_number"], c)) for c in info["codes"]) if p.exists()]


@router.post("/incidents/{incident_number}/camera/attach")
def camera_attach(incident_number: str):
    """Anexa ao incidente os snapshots já gerados (pula os que já estão anexados). Respeita o dry-run."""
    info = _resolve(incident_number)
    if not info["sys_id"]:
        raise HTTPException(status_code=409, detail="sys_id ausente")
    files = _arquivos(info)
    if not files:
        raise HTTPException(status_code=422, detail="Nenhum snapshot gerado para este incidente")
    try:
        existentes = sn_api.list_attachment_names(info["sys_id"])
        if existentes is None:
            raise HTTPException(status_code=502, detail="Não consegui listar os anexos atuais; nada foi enviado")
        resultado = []
        for code, path in files:
            if path.name in existentes:
                resultado.append({"codigo": code, "arquivo": path.name, "status": "já anexado"})
            elif sn_api.attach_file(info["sys_id"], path.name, path.read_bytes()):
                resultado.append({"codigo": code, "arquivo": path.name, "status": "anexado"})
            else:
                resultado.append({"codigo": code, "arquivo": path.name, "status": "falhou"})
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar")
    dry = config.SERVICENOW_DRY_RUN or config.SERVICENOW_MOCK
    db.add_history(info["incident_number"], "snapshot_anexo",
                   f"dry_run={dry} " + "; ".join(f"{r['arquivo']}={r['status']}" for r in resultado), False, 0)
    return {"resultado": resultado, "dry_run": dry}


def closing_text(codes: list[str], causa: str | None = None, sem_sinal: list[str] | None = None) -> str:
    """Encerramento de câmera testada no Digifort (manual: verificado e já operando). Câmera sem print vira pendência
    com [RITM] a preencher."""
    return textos.camera_verificada(causa, codes, sem_sinal)


def _causa(info: dict) -> str | None:
    from backend.payload import mapa_localidade
    cidade = mapa_localidade(info.get("localidade")).get("cidade") or info.get("localidade")
    return textos.causa_do_titulo(info.get("titulo") or "", cidade)


@router.get("/incidents/{incident_number}/camera/closing-draft")
def closing_draft(incident_number: str):
    """Texto de encerramento no padrão do manual com as câmeras que geraram snapshot. Não grava nada."""
    info = _resolve(incident_number)
    com_print = [c for c, _ in _arquivos(info)]
    if not com_print:
        raise HTTPException(status_code=422, detail="Nenhum snapshot gerado: teste a câmera antes")
    faltando = [c for c in info["codes"] if c not in com_print]
    texto = closing_text(com_print, _causa(info), faltando)
    return {"texto": texto, "faltando": faltando, "avisos": textos.revisar(texto)[1]}


def _ja_registrada(texto: str, atual: dict) -> bool:
    """A nota já está no incidente? Compara a 1ª linha (Causa raiz, com as câmeras): o Encerramento é igual em todas."""
    primeira = next((l.strip() for l in texto.splitlines() if l.strip()), "")
    return bool(primeira) and primeira.lower() in (atual.get("work_notes") or "").lower()


def preparar_texto(texto: str, validacao: str | None) -> tuple[str, list[str]]:
    """Revisão do manual + Validação; recusa colchete de modelo não preenchido (nada vai ao ServiceNow)."""
    t, avisos = textos.revisar(textos.com_validacao(texto.strip(), validacao))
    falta = textos.bloqueios(t)
    if falta:
        raise HTTPException(status_code=422, detail=f"Preencha {', '.join(falta)} antes de enviar")
    return t, avisos


@router.post("/incidents/{incident_number}/camera/closing-note")
def closing_note(incident_number: str, body: NotaIn):
    """Registra a work note de encerramento (só work note: não muda estado nem encerra). Exige o print já anexado.
    Não repete a nota se já existir. Respeita o dry-run."""
    info = _resolve(incident_number)
    if len(body.texto.strip()) < 20:
        raise HTTPException(status_code=422, detail="Texto muito curto")
    texto, _ = preparar_texto(body.texto, body.validacao)
    if not info["sys_id"]:
        raise HTTPException(status_code=409, detail="sys_id ausente")
    files = _arquivos(info)
    dry = config.SERVICENOW_DRY_RUN or config.SERVICENOW_MOCK
    try:
        anexos = sn_api.list_attachment_names(info["sys_id"])
        if anexos is None:
            raise HTTPException(status_code=502, detail="Não consegui conferir os anexos; nada foi enviado")
        if not dry and not any(p.name in anexos for _, p in files):
            raise HTTPException(status_code=409, detail="Anexe o print ao incidente antes de registrar a nota de encerramento")
        atual = sn_api.get_current(info["sys_id"])
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar")
    if atual is None:
        raise HTTPException(status_code=502, detail="Não consegui ler o incidente; nada foi enviado")
    if _ja_registrada(texto, atual):
        return {"status": "já registrada", "dry_run": dry}
    if not sn_api.patch_incident(info["sys_id"], {"work_notes": texto}):
        raise HTTPException(status_code=502, detail="Falha ao gravar a work note no ServiceNow")
    db.add_history(info["incident_number"], "nota_encerramento", f"dry_run={dry} {texto[:200]}", False, 0)
    return {"status": "registrada", "dry_run": dry}


@router.post("/incidents/{incident_number}/camera/close")
def camera_close(incident_number: str, body: NotaIn):
    """Encerra (Resolvido, fluxo 9.3) o incidente de câmera que voltou: state 6, close_code Solved, close_notes e work
    note com o texto. Exige o print já anexado e confere no ServiceNow se já está encerrado. Respeita o dry-run.
    Pedido explícito do Victor = gesto de segurar no painel."""
    from backend import fluxo
    from backend.payload import ASSIGNED_TO
    from backend.routes.incidents import CLOSE_CODE
    info = _resolve(incident_number)
    if len(body.texto.strip()) < 20:
        raise HTTPException(status_code=422, detail="Texto de encerramento muito curto")
    texto, _ = preparar_texto(body.texto, body.validacao)
    if not info["sys_id"]:
        raise HTTPException(status_code=409, detail="sys_id ausente")
    files = _arquivos(info)
    if not files:
        raise HTTPException(status_code=422, detail="Teste a câmera e gere o print antes de encerrar")
    dry = config.SERVICENOW_DRY_RUN or config.SERVICENOW_MOCK
    try:
        anexos = sn_api.list_attachment_names(info["sys_id"])
        if anexos is None:
            raise HTTPException(status_code=502, detail="Não consegui conferir os anexos; nada foi enviado")
        if not dry and not any(p.name in anexos for _, p in files):
            raise HTTPException(status_code=409, detail="Anexe o print ao incidente antes de encerrar")
        atual = sn_api.get_current(info["sys_id"])
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar")
    if atual is None:
        raise HTTPException(status_code=502, detail="Não consegui ler o incidente; nada foi enviado")
    estado = str(atual.get("state") or "")
    if estado in fluxo.ESTADOS_ENCERRADOS:
        return {"status": "já encerrado", "dry_run": dry, "estado": estado}
    payload = {"state": "6", "close_code": CLOSE_CODE, "close_notes": texto,
               "u_is_recurring_incident": "no", "assigned_to": ASSIGNED_TO}
    if not _ja_registrada(texto, atual):
        payload["work_notes"] = texto  # a nota já registrada não se repete
    try:
        if not sn_api.patch_incident(info["sys_id"], payload):
            raise HTTPException(status_code=502, detail="ServiceNow recusou o encerramento; nada mudou")
    except SNAuthError:
        raise HTTPException(status_code=409, detail="ServiceNow desconectado: clique em Conectar")
    if info["local"] and not dry:
        inc = db.get_incident(info["incident_number"]) or {}
        db.set_fluxo(info["incident_number"], fluxo.ENCERRADO, "6", inc.get("sn_grupo") or info.get("grupo") or "",
                     inc.get("nota_autor"))
    db.add_history(info["incident_number"], "encerrado", f"camera dry_run={dry} state=6 close_code={CLOSE_CODE} nota={texto[:100]}")
    return {"status": "encerrado", "dry_run": dry, "fields": payload}

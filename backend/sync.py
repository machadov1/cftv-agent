"""Busca incidentes novos da fila geral (AMS-TI-CFTV) e analisa cada um. SOMENTE LEITURA no ServiceNow."""
import re
import threading
import time

from backend import db, fluxo, learning
from backend.payload import camera_codes
from backend.scom import is_scom_alert
from backend.analysis import analyze
from backend.config import config
from backend.servicenow_api import sn_api, SNAuthError
from backend.sn_session import session

# Skill (regra 9): RFID de empilhadeira e Safe Zone não são CFTV: não importar, só reportar
NON_CFTV = re.compile(r"RFID|empilhadeira|safe\s*zone", re.IGNORECASE)
MAX_LLM_PER_RUN = 5  # a busca em lote não pode virar uma rajada de chamadas ao LLM

_lock = threading.Lock()
_state = {"running": False, "last_run": None, "last_ok": None, "novos": [], "novos_total": 0,
          "ignorados": [], "sairam": [], "conhecidos": 0, "total_fila": 0, "erro": None}


def status() -> dict:
    return {**_state, "grupo": config.QUEUE_GROUP, "intervalo_s": config.SYNC_INTERVAL,
            "auto": not config.SERVICENOW_MOCK}


def is_cftv(sn_incident: dict) -> bool:
    text = f"{sn_incident.get('short_description') or ''} {sn_incident.get('description') or ''}"
    return not NON_CFTV.search(text)


def _backfill_cameras() -> None:
    """Relê o código da câmera dos pendentes em que a leitura falhou antes e reavalia os que estavam sem destino."""
    try:
        for r in db.incidents_sem_camera():
            cam = sn_api.get_camera_code(r["sys_id"])
            if cam is None:
                continue
            if cam == "" and not is_scom_alert(r["short_description"] or "", r["description"] or ""):
                cam = ", ".join(camera_codes(None, r["short_description"] or "", r["description"] or ""))
            db.set_camera(r["incident_number"], cam)
        learning.reaplicar_sem_destino()
    except SNAuthError:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"backfill de câmeras: {e}")


def run_sync() -> dict:
    """Uma rodada: lista a fila, analisa o que ainda não conhecemos. Ignora se já houver uma em curso."""
    if not _lock.acquire(blocking=False):
        return status()
    try:
        _state.update(running=True, erro=None)
        rows = sn_api.list_queue()
        eu = sn_api.meu_nome()
        novos, ignorados, conhecidos, llm, fora = [], [], 0, 0, []
        for r in rows:
            n = r.get("number")
            if not n:
                continue
            if db.get_incident(n):
                conhecidos += 1
                continue
            if not is_cftv(r):
                ignorados.append({"incident_number": n, "short_description": r.get("short_description")})
                continue
            # já tem nota minha (tratei direto no ServiceNow): registra, mas não entra na Entrada nem gasta LLM
            minha = bool(eu) and eu in fluxo.autores(r.get("work_notes"))
            res = analyze(n, r, allow_llm=not minha and llm < MAX_LLM_PER_RUN)
            llm += 1 if res["chamou_claude"] else 0
            if minha:
                db.set_fluxo(n, fluxo.FORA, str(r.get("state") or ""), r.get("assignment_group") or "", eu)
                fora.append(n)
            else:
                novos.append(n)
        rec = fluxo.reconciliar()
        _backfill_cameras()
        _state.update(last_ok=time.time(), novos=novos, novos_total=_state["novos_total"] + len(novos),
                      ignorados=ignorados, conhecidos=conhecidos, total_fila=len(rows),
                      sairam=[m[0] for m in rec["mudaram"] if m[1] == fluxo.ENTRADA] + fora)
    except SNAuthError:
        _state["erro"] = "ServiceNow desconectado: clique em Conectar."
    except Exception as e:  # noqa: BLE001
        _state["erro"] = f"Falha ao buscar a fila: {e}"
    finally:
        _state.update(running=False, last_run=time.time())
        _lock.release()
    return status()


def start_loop() -> None:
    """Busca periódica em segundo plano, só com o ServiceNow conectado (nunca em mock)."""
    if config.SERVICENOW_MOCK:
        return

    def loop():
        while True:
            time.sleep(15)
            due = _state["last_run"] is None or time.time() - _state["last_run"] >= config.SYNC_INTERVAL
            if session.connected and due:
                run_sync()

    threading.Thread(target=loop, daemon=True).start()

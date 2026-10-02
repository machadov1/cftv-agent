"""Análise de um incidente já lido do ServiceNow: regras primeiro, LLM só se a confiança for baixa."""
import time

from backend import db
from backend.claude_caller import call_claude_for_localidade, call_claude_for_ritm
from backend.config import config
from backend.rules_engine import engine
from backend.payload import camera_codes
from backend.scom import is_scom_alert
from backend.servicenow_api import sn_api


def _sugestao(r: dict) -> str:
    return f"Fila: {r.get('grupo_display') or '—'}, RITM: {'SIM' if r.get('ritm_necessaria') else 'NÃO'}"


def _texto(v) -> str:
    """Campo de referência: dict {display_value, value} ou já texto."""
    if isinstance(v, dict):
        return v.get("display_value") or ""
    return str(v or "")


def analyze(number: str, sn_incident: dict, *, allow_llm: bool = True, persist: bool = True) -> dict:
    """Aplica as regras e (se persist) salva a sugestão e registra no histórico. Não escreve no ServiceNow."""
    start = time.perf_counter()

    # Extrair localidade do incidente se existir
    loc_field = sn_incident.get("u_incident_location", {})
    incident_location = loc_field.get("display_value") if isinstance(loc_field, dict) else str(loc_field or "")

    short, desc = sn_incident.get("short_description", ""), sn_incident.get("description", "")
    camera = sn_api.get_camera_code(sn_incident.get("sys_id")) if persist else None
    if camera == "" and not is_scom_alert(short, desc):  # formulário sem código: vale o que o texto cita
        camera = ", ".join(camera_codes(None, short, desc))

    result = engine.apply_rules({
        "short_description": short,
        "description": desc,
        "u_incident_location": incident_location,
        "camera_codigo": camera,
        "caller_id": _texto(sn_incident.get("caller_id")),
        "cmdb_ci": _texto(sn_incident.get("cmdb_ci")),
        "cmdb_ci_location": _texto(sn_incident.get("cmdb_ci.location")),
        "caller_location": _texto(sn_incident.get("caller_id.location")),
    })
    conflito = result.pop("conflito", False)

    chamou_claude = False
    # pistas em conflito (IC x texto) ficam para o Victor decidir: o LLM não desempata
    if allow_llm and not conflito and result["localidade_confianca"] < config.CONFIDENCE_THRESHOLD and config.llm_enabled:
        chamou_claude = True
        desc = sn_incident.get("short_description", "")
        try:
            localidade = call_claude_for_localidade(desc, engine.known_localidades() or None)
            if localidade:
                grupo, grupo_display = engine.find_group_for_localidade(localidade)
                result.update(localidade=localidade, localidade_confianca=70,
                              grupo=grupo, grupo_display=grupo_display)
                result["motivo"] += f" | LLM: {localidade}"
                if not result["ritm_necessaria"]:
                    result["ritm_necessaria"] = call_claude_for_ritm(desc, localidade)
        except Exception as e:
            result["motivo"] += f" | Falha no LLM: {e}"

    elapsed_ms = (time.perf_counter() - start) * 1000
    if not persist:
        return {"incident_number": number, "short_description": sn_incident.get("short_description"), **result,
                "chamou_claude": chamou_claude, "tempo_ms": round(elapsed_ms, 1), "sugestao": _sugestao(result)}
    # Extrair nome do solicitante (caller_id pode ser dict ou string)
    caller = sn_incident.get("caller_id", {})
    caller_name = caller.get("display_value") if isinstance(caller, dict) else str(caller or "")

    # Extrair data de abertura
    opened = sn_incident.get("opened_at", {})
    opened_at = opened.get("value") if isinstance(opened, dict) else str(opened or "")
    due = sn_incident.get("due_date", {})
    due_date = (due.get("value") if isinstance(due, dict) else str(due or "")) or None  # vencimento do SLA (UTC)

    db.save_incident(number, {
        "sys_id": sn_incident.get("sys_id"),
        "short_description": sn_incident.get("short_description"),
        "description": sn_incident.get("description"),
        "opened_at": opened_at,
        "due_date": due_date,
        "caller_id": caller_name,
        "u_incident_location": incident_location,
        "subcategory": sn_incident.get("subcategory"),
        "camera_codigo": camera,
        "cmdb_ci": _texto(sn_incident.get("cmdb_ci")),
        "u_informal_service": str(sn_incident.get("u_informal_service")).lower() in ("true", "1", "yes"),
        **result,
    })
    db.add_history(number, "analise", result["motivo"], chamou_claude, elapsed_ms)

    return {
        "incident_number": number,
        "short_description": sn_incident.get("short_description"),
        **result,
        "chamou_claude": chamou_claude,
        "tempo_ms": round(elapsed_ms, 1),
        "sugestao": _sugestao(result),
    }

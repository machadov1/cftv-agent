"""Painel de backlog (inspirado no 'Painel de Controle - CFTV' do ServiceNow). SOMENTE LEITURA.

Carga aberta das filas AMS-TI-CFTV*, com prazo (hoje / amanhã / vencido), equipe e encerrados no mês.
"""
import re
import time
from datetime import datetime, timedelta, timezone

from backend.config import config
from backend import db, filas
from backend.payload import relevant_text
from backend.rules_engine import engine
from backend.servicenow_api import sn_api

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("America/Sao_Paulo")
except Exception:  # Windows sem tzdata: Brasil sem horário de verão desde 2019
    _TZ = timezone(timedelta(hours=-3))

CACHE_TTL = 60  # s: o painel atualiza a cada minuto, sem martelar o ServiceNow
_cache: dict = {"at": 0.0, "data": None}

def _f(r: dict, name: str, key: str = "display_value"):
    x = r.get(name)
    return x.get(key) if isinstance(x, dict) else x


def _utc(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(_TZ)
    except ValueError:
        return None


def prazo(due: datetime | None, now: datetime) -> tuple[str, str]:
    """(estado, texto): vencido | hoje | amanha | ok | sem_prazo"""
    if not due:
        return "sem_prazo", "—"
    dias = (due.date() - now.date()).days
    if due < now:
        d = (now.date() - due.date()).days
        return "vencido", "vencido hoje" if d == 0 else f"vencido há {d}d"
    if dias == 0:
        return "hoje", f"hoje {due:%H:%M}"
    if dias == 1:
        return "amanha", f"amanhã {due:%H:%M}"
    return "ok", f"{due:%d/%m %H:%M}"


def _truthy(x) -> bool:
    return str(x).strip().lower() in ("true", "verdadeiro(a)", "verdadeiro", "1", "yes")


def _ultima_nota(texto: str | None) -> str | None:
    """Primeira linha do diário (comentários + notas de trabalho): 'data - autor'. O ServiceNow lista a mais recente primeiro."""
    if not texto:
        return None
    linha = texto.strip().splitlines()[0]
    linha = re.sub(r"\s*\((?:Anotações de trabalho|Comentários adicionais|Work notes|Additional comments)\)\s*$", "", linha)
    return linha[:70]


def normalize(r: dict, now: datetime) -> dict:
    due = _utc(_f(r, "due_date", "value"))
    opened = _utc(_f(r, "opened_at", "value"))
    estado, texto = prazo(due, now)
    violado = _truthy(_f(r, "u_has_breached", "value"))
    if violado and estado != "vencido":  # SLA violado no ServiceNow manda mais que a conta por data
        estado, texto = "vencido", "SLA violado"
    grupo = _f(r, "assignment_group") or ""
    return {
        "number": _f(r, "number"),
        "titulo": _f(r, "short_description"),
        "solicitante": _f(r, "caller_id"),
        "aberto": opened.isoformat() if opened else None,
        "prazo": due.isoformat() if due else None,
        "prazo_estado": estado,
        "prazo_txt": texto,
        "status": _f(r, "state"),
        "grupo": grupo,
        "equipe": filas.team_of(grupo),
        "prioridade": _f(r, "priority"),
        "atualizado_por": _f(r, "sys_updated_by"),
        "sla_violado": violado,
        "informal": _truthy(_f(r, "u_informal_service", "value")),
        "ultima_nota": _ultima_nota(_f(r, "comments_and_work_notes")),
        "descricao": re.sub(r"\s+", " ", relevant_text(_f(r, "description") or "")).strip()[:300],
        "localidade": engine.apply_rules({"short_description": _f(r, "short_description") or "",
                                          "description": _f(r, "description") or ""})["localidade"],
    }


def summarize(rows: list[dict], now: datetime, encerrados_mes: int | None) -> dict:
    por_equipe = {t: 0 for t in filas.equipes()}
    dias: dict[str, int] = {}
    for r in rows:
        por_equipe[r["equipe"]] += 1
        if r["prazo"] and r["prazo_estado"] != "vencido":
            k = r["prazo"][:10]
            dias[k] = dias.get(k, 0) + 1
    hoje = now.date()
    calendario = [{"dia": (hoje + timedelta(days=i)).isoformat(),
                   "total": dias.get((hoje + timedelta(days=i)).isoformat(), 0)} for i in range(7)]
    return {
        "backlog_total": len(rows),
        "vencidos": sum(r["prazo_estado"] == "vencido" for r in rows),
        "encerrar_hoje": sum(r["prazo_estado"] == "hoje" for r in rows),
        "encerrar_amanha": sum(r["prazo_estado"] == "amanha" for r in rows),
        "encerrados_mes": encerrados_mes,
        "por_equipe": [{"equipe": t, "total": n} for t, n in por_equipe.items()],
        "calendario": calendario,
        "vencidos_calendario": sum(r["prazo_estado"] == "vencido" for r in rows),
    }


def _mock_rows(now: datetime) -> list[dict]:
    def raw(n, t, who, off_h, grupo, st, pr):
        due = (now + timedelta(hours=off_h)).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        op = (now - timedelta(days=2)).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        return {"number": n, "short_description": t, "caller_id": {"display_value": who},
                "due_date": {"value": due}, "opened_at": {"value": op}, "assignment_group": {"display_value": grupo},
                "state": {"display_value": st}, "priority": {"display_value": pr}, "sys_updated_by": "vic.machado"}
    return [normalize(x, now) for x in [
        raw("INC9100001", "Barra Mansa - Câmera BM-LAM2-H-035 sem conexão", "Lourenço, Alexandre", -30, "AMS-TI-CFTV-DBB", "Em Andamento", "3 - Médio"),
        raw("INC9100002", "Barra Mansa - Câmera BM-LAM2-H-036 sem conexão", "Lourenço, Alexandre", 3, "AMS-TI-CFTV-DBB", "Em Andamento", "3 - Médio"),
        raw("INC9100003", "Barra Mansa - Câmera BM-LAM2-H-037 sem conexão", "Lourenço, Alexandre", 5, "AMS-TI-CFTV-DBB", "Em Andamento", "3 - Médio"),
        raw("INC9100004", "Piracicaba - Servidor do Pátio Metálicos offline", "Dutra, Tulio", 6, "AMS-TI-CFTV-PIR", "Em Andamento", "3 - Médio"),
        raw("INC9100005", "Piracicaba - Câmeras PR421/PR420 sem conexão", "Morais, Mauricio", 26, "AMS-TI-CFTV-PIR", "Novo", "3 - Médio"),
        raw("INC9100006", "Resende - Câmeras RES024/RES025 sem conexão", "Ambroseto, Guilherme", 27, "AMS-TI-CFTV-DBC", "Em Andamento", "3 - Médio"),
        raw("INC9100007", "Rio das Pedras - Câmeras do quadro 05 sem conexão", "Souza, John", -5, "AMS-TI-CFTV-RDP", "Em Andamento", "4 - Baixo"),
        raw("INC9100008", "Juiz de Fora - Fibra rompida no trecho da portaria", "Silva, Rafael", 52, "AMS-TI-CFTV-JUA", "Em Andamento", "2 - Alto"),
        raw("INC9100009", "João Monlevade - Câmera MDE-012 sem movimentação PTZ", "Santos, Juliano", 76, "AMS-TI-CFTV-MDE", "Novo", "3 - Médio"),
        raw("INC9100010", "Jaboatão - Servidor sem conexão", "Rocha, Robson", 30, "AMS-TI-CFTV-JAB", "Novo", "3 - Médio"),
        raw("INC9100011", "Piracicaba - TAG LORA 808 - Falha de funcionalidade", "Silva, Ana", 28, "AMS-TI-LORA-PIR", "Em Andamento", "4 - Baixo"),
        raw("INC9100012", "Guarulhos - Câmeras sem conexão", "Costa, Ericon", 8, "AMS-TI-A4-GUA", "Novo", "3 - Médio"),
    ]]


def get_backlog(force: bool = False) -> dict:
    """KPIs + linhas do backlog. Cache curto; erro de sessão sobe como SNAuthError."""
    if not force and _cache["data"] and time.time() - _cache["at"] < CACHE_TTL:
        return _cache["data"]
    now = datetime.now(_TZ)
    if config.SERVICENOW_MOCK:
        rows, mes = _mock_rows(now), 347
    else:
        rows = [normalize(r, now) for r in sn_api.list_backlog()]
        mes = sn_api.count_closed_month()
    rows.sort(key=lambda r: (r["prazo"] is None, r["prazo"] or ""))
    data = {"atualizado_em": now.isoformat(), "kpis": summarize(rows, now, mes), "rows": rows, "equipes": filas.equipes()}
    _cache.update(at=time.time(), data=data)
    if not config.SERVICENOW_MOCK:
        _snapshot(rows, now)
    return data


def _snapshot(rows: list[dict], now: datetime) -> None:
    """Retrato do dia para a tendência nas métricas (falha aqui nunca derruba o painel)."""
    try:
        idades = [(now - datetime.fromisoformat(r["aberto"])).total_seconds() / 3600 for r in rows if r["aberto"]]
        db.save_backlog_snapshot(
            now.date().isoformat(), len(rows), sum(r["prazo_estado"] == "vencido" for r in rows),
            sum((r["status"] or "").lower() == "novo" for r in rows),
            sum("andamento" in (r["status"] or "").lower() for r in rows),
            round(sum(idades) / len(idades), 1) if idades else 0.0, [r["number"] for r in rows if r["number"]])
    except Exception as e:  # noqa: BLE001
        print(f"retrato do backlog: {e}")

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend import backlog
from backend.config import config

TZ = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 9, 30, 10, 0, tzinfo=TZ)


def _utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def test_prazo_estados():
    assert backlog.prazo(AGORA - timedelta(hours=3), AGORA) == ("vencido", "vencido hoje")
    assert backlog.prazo(AGORA - timedelta(days=2), AGORA)[1] == "vencido há 2d"
    assert backlog.prazo(AGORA + timedelta(hours=4), AGORA)[0] == "hoje"
    assert backlog.prazo(AGORA + timedelta(hours=20), AGORA)[0] == "amanha"
    assert backlog.prazo(AGORA + timedelta(days=4), AGORA)[0] == "ok"
    assert backlog.prazo(None, AGORA) == ("sem_prazo", "—")


def test_equipes_como_no_painel_do_servicenow():
    assert [backlog.filas.team_of(g) for g in ("AMS-TI-CFTV-JUA", "AMS-TI-CFTV-DBB", "AMS-TI-CFTV-DBC", "AMS-TI-CFTV-PIR", "AMS-TI-CFTV-MDE")] == ["JDF", "BMA", "RSD", "PIR", "MDE"]
    f = backlog.filas.team_of
    # filas reais do board que antes ficavam de fora
    assert [f(g) for g in ("AMS-TI-LORA-PIR", "AMS-TI-A4-GUA", "AMS-TI-4OLHOS-BBD (Bauru)", "FCB-INFRA-CFTV-PEC", "AMS-TI-CFTV")] == ["LORA", "A4", "4 OLHOS", "PEC", "Geral"]
    assert f("AMS-TI-CFTV-RDP") == "Outras" and f(None) == "Outras"


def test_filtro_identico_ao_board_do_servicenow():
    q = backlog.filas.grupos_query()
    for trecho in ("assignment_group.nameSTARTSWITHAMS-TI-CFTV", "nameLIKELORA", "nameLIKEalert", "nameLIKEAMPE-TI-CFTV",
                   "nameLIKEAMS-TI-A4", "nameLIKEAMS-TI-4OLHOS", "nameLIKEFCB-INFRA-CFTV-PEC"):
        assert trecho in q
    assert backlog.filas.estados_fora() == "6,7,24"  # 6 Resolvido, 7 Encerrado, 24 Cancelado (o 8 é "Aguardando Mudança", não cancelado)


def test_normaliza_formato_do_servicenow_e_resume():
    def raw(n, off, grupo):
        return {"number": n, "short_description": f"t{n}", "caller_id": {"display_value": "Fulano", "value": "x"},
                "due_date": {"value": _utc(AGORA + timedelta(hours=off)), "display_value": "..."},
                "opened_at": {"value": _utc(AGORA - timedelta(days=1))},
                "assignment_group": {"display_value": grupo}, "state": {"display_value": "Em Andamento"},
                "priority": {"display_value": "3 - Médio"}, "sys_updated_by": "vic"}
    rows = [backlog.normalize(r, AGORA) for r in (raw("A", -2, "AMS-TI-CFTV-DBB"), raw("B", 3, "AMS-TI-CFTV-DBB"),
                                                   raw("C", 20, "AMS-TI-CFTV-PIR"))]
    k = backlog.summarize(rows, AGORA, 347)
    assert (k["backlog_total"], k["vencidos"], k["encerrar_hoje"], k["encerrar_amanha"], k["encerrados_mes"]) == (3, 1, 1, 1, 347)
    assert {e["equipe"]: e["total"] for e in k["por_equipe"]}["BMA"] == 2
    assert len(k["calendario"]) == 7 and sum(d["total"] for d in k["calendario"]) == 2  # vencido fica fora do calendário


def test_endpoint_em_mock_e_sessao_expirada(monkeypatch):
    from backend.main import app
    c = TestClient(app)
    monkeypatch.setattr(config, "SERVICENOW_MOCK", True)
    backlog._cache.update(at=0.0, data=None)
    d = c.get("/backlog?force=true").json()
    assert d["kpis"]["backlog_total"] == 12 and d["kpis"]["vencidos"] >= 1 and d["rows"][0]["prazo_estado"] == "vencido"

    from backend.servicenow_api import SNAuthError
    monkeypatch.setattr(config, "SERVICENOW_MOCK", False)
    monkeypatch.setattr(backlog.sn_api, "list_backlog", lambda: (_ for _ in ()).throw(SNAuthError("401")))
    r = c.get("/backlog?force=true")
    assert r.status_code == 409 and "Conectar" in r.json()["detail"]
    backlog._cache.update(at=0.0, data=None)


def test_sla_violado_e_ultima_nota_do_servicenow():
    def raw(breached):
        return {"number": "INC1", "short_description": "t", "caller_id": {"display_value": "F"},
                "due_date": {"value": _utc(AGORA + timedelta(days=3))}, "opened_at": {"value": _utc(AGORA)},
                "assignment_group": {"display_value": "AMS-TI-LORA-PIR"}, "state": {"display_value": "Em Andamento"},
                "priority": {"display_value": "4 - Baixo"}, "sys_updated_by": "vic",
                "u_has_breached": {"value": breached}, "u_informal_service": {"value": "false"},
                "comments_and_work_notes": {"display_value": "28/09/2026 16:36:44 - Machado, Victor (Anotações de trabalho)\nEncaminhado para equipe."}}
    r = backlog.normalize(raw("true"), AGORA)
    assert r["sla_violado"] and r["prazo_estado"] == "vencido" and r["prazo_txt"] == "SLA violado"  # vence só daqui 3 dias, mas o SLA já estourou
    assert r["ultima_nota"] == "28/09/2026 16:36:44 - Machado, Victor" and r["equipe"] == "LORA" and not r["informal"]
    assert backlog.normalize(raw("false"), AGORA)["prazo_estado"] == "ok"

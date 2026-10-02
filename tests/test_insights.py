"""Insights das Métricas com dados sintéticos (sem ServiceNow, sem planilha real)."""
from datetime import datetime, timedelta, timezone

from backend import insights

BRT = timezone(timedelta(hours=-3))
NOW = datetime(2026, 10, 1, 15, 0, tzinfo=BRT)


def row(n, titulo, equipe="BMA", prazo_h=24, estado="amanha", status="Em Andamento", aberto_d=1, nota=None,
        grupo="AMS-TI-CFTV-DBB", loc="Barra Mansa"):
    return {"number": n, "titulo": titulo, "equipe": equipe, "prazo": (NOW + timedelta(hours=prazo_h)).isoformat(),
            "prazo_estado": estado, "prazo_txt": "", "status": status, "aberto": (NOW - timedelta(days=aberto_d)).isoformat(),
            "ultima_nota": nota, "grupo": grupo, "localidade": loc, "descricao": ""}


def test_area():
    assert insights.area("BM-PAT-G-052") == "BM-PAT"
    assert insights.area("BM-LAM-CLI-049") == "BM-LAM-CLI"
    assert insights.area("RES027") == "RES"
    assert insights.area("03-SUC") == "SUC"


def test_onda_sla_e_vencidos():
    rows = [row(f"INC{i}", "x", prazo_h=20 + i) for i in range(5)] + \
           [row("INC9", "y", equipe="LORA", prazo_h=60), row("INC8", "z", prazo_h=-2, estado="vencido")]
    o = insights.onda_sla(rows, NOW)
    assert o["pico"]["dia"] == "2026-10-02" and o["pico"]["total"] == 5
    assert o["pico"]["por_equipe"][0] == {"equipe": "BMA", "total": 5}
    assert [v["number"] for v in o["vencidos"]] == ["INC8"]
    assert len(o["serie"]) == 7


def test_diagnostico_e_cameras_para_agir():
    hist = [
        {"incident_number": "INC1", "acao": "snapshot", "resultado": "BM-1: Câmera ainda sem sinal no Digifort; snapshot não gerado", "created_at": "2026-10-01 10:00:00"},
        {"incident_number": "INC1", "acao": "snapshot", "resultado": "BM-1: ok", "created_at": "2026-10-01 12:00:00"},
        {"incident_number": "INC2", "acao": "snapshot", "resultado": "BM-2: Câmera DESATIVADA no cadastro do Digifort; snapshot não gerado; BM-4: ok", "created_at": "2026-10-01 12:00:00"},
        {"incident_number": "INC3", "acao": "snapshot", "resultado": "BM-3: ok", "created_at": "2026-10-01 12:00:00"},
        {"incident_number": "INC3", "acao": "nota_encerramento", "resultado": "", "created_at": "2026-10-01 12:05:00"},
    ]
    rows = [row("INC1", "a"), row("INC2", "b"), row("INC3", "c")]
    c = insights.cameras_acao(rows, insights.diagnostico_cameras(hist))
    assert [x["number"] for x in c["voltou"]] == ["INC1"]  # INC3 já tem a nota: não repete
    assert [x["number"] for x in c["desativada"]] == ["INC2"]
    assert c["desativada"][0]["cameras"] == {"BM-2": "desativada", "BM-4": "ok"}


def test_parados_pela_ultima_nota():
    rows = [row("INC1", "a", nota="28/09/2026 10:00:00 - Fulano"), row("INC2", "b", nota="01/10/2026 10:00:00 - Fulano"),
            row("INC3", "c", status="Novo", aberto_d=5)]
    p = insights.parados(rows, NOW)
    assert [x["number"] for x in p["itens"]] == ["INC1"]


def test_ritms_vencendo_e_pendencias():
    base = {"situacao": "Aberta", "unidade": "Resende", "descricao": "Câmera RES024", "req": "REQ", "inc": "INC1"}
    rows = [{**base, "ritm": "RITM1", "pendencia": "PEMT", "abertura": datetime(2026, 9, 13), "fechamento": datetime(2026, 10, 3)},
            {**base, "ritm": "RITM2", "pendencia": "PEMT", "abertura": datetime(2026, 9, 1), "fechamento": datetime(2026, 9, 21)},
            {**base, "ritm": "RITM3", "pendencia": "Elétrica", "abertura": datetime(2026, 9, 30), "fechamento": datetime(2026, 10, 20)}]
    r = insights.ritms(rows, NOW)
    assert [x["ritm"] for x in r["vencendo"]] == ["RITM1"]
    assert [x["ritm"] for x in r["vencidas"]] == ["RITM2"]
    assert r["por_pendencia"][0] == {"pendencia": "PEMT", "total": 2}


def test_cronicas_cruzam_fila_backlog_e_ritm():
    local = [{"incident_number": "INC1", "localidade": "Barra Mansa", "camera_codigo": "BM-PAT-G-052",
              "short_description": "", "description": "", "status": "aprovado"}]
    rows = [row("INC2", "Barra Mansa - Câmera BM-PAT-G-052 sem conexão")]
    ritm = [{"inc": "INC3", "ritm": "RITM9", "unidade": "Barra Mansa", "descricao": "Câmera BM-PAT-G-052 sem conexão"}]
    cams = insights._cameras_por_incidente(rows, local, ritm)
    cr = insights.cameras_cronicas(cams)
    assert cr[0]["camera"] == "BM-PAT-G-052" and len(cr[0]["incidentes"]) == 3
    assert insights.pontos_quentes(cams)[0]["area"] == "BM-PAT"


def test_tendencia_entradas_e_saidas():
    snaps = [{"dia": "2026-10-01", "total": 3, "vencidos": 0, "idade_media_h": 10, "numeros": ["A", "B", "C"]},
             {"dia": "2026-10-02", "total": 3, "vencidos": 1, "idade_media_h": 20, "numeros": ["B", "C", "D"]}]
    t = insights.tendencia(snaps)
    assert t["serie"][1]["entraram"] == 1 and t["serie"][1]["sairam"] == 1 and t["serie"][0]["entraram"] is None


def test_painel_sem_backlog_nao_quebra():
    p = insights.painel(None, [], [], [], [], [], NOW)
    assert p["backlog_total"] == 0 and p["agir"]["onda"]["pico"] is None

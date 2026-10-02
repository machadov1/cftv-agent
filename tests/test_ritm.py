import shutil

import pytest
from fastapi.testclient import TestClient

from backend.config import config, ROOT
from backend import ritm


@pytest.fixture()
def client(tmp_path, monkeypatch):
    rules = tmp_path / "rules.json"
    shutil.copy(ROOT / "data" / "rules.json", rules)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "RULES_PATH", str(rules))
    monkeypatch.setattr(config, "SERVICENOW_DRY_RUN", True)
    monkeypatch.setattr(config, "SERVICENOW_MOCK", True)  # find_today usa a lista mock
    monkeypatch.setattr(ritm, "_MOCK_RITMS", [])

    from backend.main import app
    from backend.db import init_db
    from backend.rules_engine import engine
    engine._mtime = None
    init_db()

    incs = {
        "INC1": {"sys_id": "s1", "short_description": "Câmeras RES024 / RES025 sem conexão", "description": ""},
        "INC2": {"sys_id": "s2", "short_description": "Câmera RES025 tela preta", "description": ""},
    }
    from backend.routes import incidents
    monkeypatch.setattr(incidents.sn_api, "get_incident", lambda n: incs.get(n))
    monkeypatch.setattr(incidents.sn_api, "get_current", lambda sid: {"state": "2", "work_notes": ""})
    monkeypatch.setattr(incidents.sn_api, "patch_incident", lambda sid, f: True)
    c = TestClient(app)
    for n in incs:
        c.post("/incidents", json={"incident_number": n})
    return c


def test_draft(client):
    d = client.get("/incidents/INC1/ritm/draft").json()
    assert d["localidade_form"] == "CFTV - Resende"
    assert d["subarea"] == "RES024 / RES025"
    assert d["descricao"].startswith("Causa raiz: Câmeras RES024/RES025 sem conexão.")
    assert any("pendência" in w for w in d["warnings"])  # pendência a escolher


def test_cria_e_bloqueia_duplicidade(client):
    d = client.get("/incidents/INC1/ritm/draft").json()
    body = {"localidade_form": d["localidade_form"], "subarea": d["subarea"], "pendencia": "PEMT",
            "descricao": ritm.render_description("INC1", d["causa"], "PEMT", "Aguardando atuação.")}
    r = client.post("/incidents/INC1/ritm", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ritm"].startswith("RITM") and j["simulado"]
    nota = j["work_note"]
    assert f"Acompanhamento seguirá vinculado à requisição {j['ritm']}." in nota  # número só no Encaminhamento
    assert nota.endswith("Encerramento: Incidente encerrado com pendência vinculada à requisição.")
    assert "Análise: Reparo depende de disponibilização de PEMT para acesso ao ponto." in nota
    assert "INC1" not in nota

    # mesmo incidente de novo
    assert client.post("/incidents/INC1/ritm", json=body).status_code == 409
    # outro incidente com câmera já coberta pela RITM de hoje
    b2 = {**body, "subarea": "RES025", "descricao": "Causa raiz: Câmera RES025 sem conexão."}
    r2 = client.post("/incidents/INC2/ritm", json=b2)
    assert r2.status_code == 409 and "RES025" in r2.json()["detail"]
    assert client.post("/incidents/INC2/ritm", json={**b2, "force": True}).status_code == 200


def test_pendencia_invalida(client):
    r = client.post("/incidents/INC1/ritm", json={"localidade_form": "x", "subarea": "x", "pendencia": "Qualquer", "descricao": "x"})
    assert r.status_code == 422


def test_teams_e_controle_em_mock(client, tmp_path, monkeypatch):
    from tests.test_step5 import _planilha
    monkeypatch.setattr(config, "CONTROLE_XLSX", _planilha(tmp_path))
    d = client.get("/incidents/INC1/ritm/draft").json()
    body = {"localidade_form": d["localidade_form"], "subarea": d["subarea"], "pendencia": "PEMT",
            "descricao": ritm.render_description("INC1", d["causa"], "PEMT", "Aguardando atuação.")}
    r = client.post("/incidents/INC1/ritm", json=body).json()
    assert r["req"].startswith("REQ")

    t = client.post("/incidents/INC1/teams-draft", json={"ritm": r["ritm"], "pendencia": "PEMT"}).json()
    assert t["aberto"] is False and r["ritm"] in t["mensagem"] and "Ericon" in t["mensagem"]
    m = t["mensagem"]
    assert "sobre o incidente INC1, câmeras RES024/RES025 sem conexão." in m
    assert "O reparo depende da disponibilização de uma PEMT para acesso ao ponto." in m
    assert f"foi aberta a requisição {r['ritm']}." in m and m.endswith("Qualquer dúvida, fico à disposição!")
    assert "pendência vinculada" not in m and t["url"].startswith("https://teams.cloud.microsoft/")

    # encerramento da Saída já sai com a RITM e a pendência usadas na criação
    cd = client.get("/incidents/INC1/close-draft").json()
    assert cd["cenario"] == "pendencia" and f"requisição {r['ritm']}." in cd["texto"] and "PEMT" in cd["texto"]

    c = client.post("/incidents/INC1/controle", json={"ritm": r["ritm"], "req": r["req"], "pendencia": "PEMT",
                                                       "subarea": d["subarea"]})
    assert c.status_code == 200
    j = c.json()
    assert j["simulado"] and not j["gravado"] and j["valores"]["H"] == "Resende"

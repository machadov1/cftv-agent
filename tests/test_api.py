import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import config, ROOT


@pytest.fixture()
def client(tmp_path, monkeypatch):
    rules = tmp_path / "rules.json"
    shutil.copy(ROOT / "data" / "rules.json", rules)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "RULES_PATH", str(rules))
    monkeypatch.setattr(config, "SERVICENOW_DRY_RUN", True)

    from backend.main import app
    from backend.db import init_db
    from backend.rules_engine import engine
    engine._mtime = None
    init_db()

    fake = {"sys_id": "abc123", "number": "INC1",
            "short_description": "CFTV offline - PIR camera 3", "description": ""}
    from backend.routes import incidents
    monkeypatch.setattr(incidents.sn_api, "get_incident", lambda n: fake if n != "INC404" else None)
    monkeypatch.setattr(incidents.sn_api, "get_current", lambda sid: {"state": "1", "work_notes": ""})
    return TestClient(app)


def test_process_matches_rule(client):
    r = client.post("/incidents", json={"incident_number": "inc1"})
    assert r.status_code == 200
    body = r.json()
    assert body["localidade"] == "Piracicaba"
    assert body["grupo_display"] == "AMS-TI-CFTV-PIR"
    assert body["chamou_claude"] is False


def test_not_found_and_invalid(client):
    assert client.post("/incidents", json={"incident_number": "INC404"}).status_code == 404
    assert client.post("/incidents", json={"incident_number": "xyz"}).status_code == 422


def test_reprocess_does_not_duplicate(client):
    client.post("/incidents", json={"incident_number": "INC1"})
    client.post("/incidents", json={"incident_number": "INC1"})
    assert len(client.get("/incidents").json()) == 1


def test_approve_and_metrics(client):
    client.post("/incidents", json={"incident_number": "INC1"})
    r = client.post("/incidents/INC1/approve")
    assert r.status_code == 200 and r.json()["dry_run"] is True and not r.json()["editado"]
    m = client.get("/metrics").json()
    assert m["total_processados"] == 1
    assert m["automacao_percentual"] == 100.0
    assert m["precisao_percentual"] == 100.0
    assert client.get("/history").json()[0]["acao"] == "aprovado"


def test_approve_edited(client):
    client.post("/incidents", json={"incident_number": "INC1"})
    r = client.post("/incidents/INC1/approve", json={"ritm_necessaria": True})
    assert r.json()["editado"] is True
    assert client.get("/metrics").json()["precisao_percentual"] == 0.0


def test_rules_crud_and_validation(client):
    assert client.post("/rules", json={"pattern": "(["}).status_code == 422
    r = client.post("/rules", json={"pattern": "BM|Barra Mansa", "localidade": "Barra Mansa",
                                    "grupo": "g", "grupo_display": "X", "ritm_necessaria": True})
    assert r.status_code == 201
    rid = r.json()["id"]
    assert client.put(f"/rules/{rid}", json={"pattern": "BM"}).status_code == 200
    assert client.delete(f"/rules/{rid}").status_code == 200
    assert client.delete(f"/rules/{rid}").status_code == 404


def test_unknown_pattern_without_llm(client, monkeypatch):
    from backend.routes import incidents
    monkeypatch.setattr(incidents.sn_api, "get_incident",
                        lambda n: {"sys_id": "x", "short_description": "algo desconhecido"})
    body = client.post("/incidents", json={"incident_number": "INC2"}).json()
    assert body["localidade"] is None and body["localidade_confianca"] == 0
    assert client.post("/incidents/INC2/approve").status_code == 422

import shutil

import pytest
from fastapi.testclient import TestClient

from backend import sync
from backend.config import config, ROOT
from backend.servicenow_api import SNAuthError


@pytest.fixture()
def env(tmp_path, monkeypatch):
    rules = tmp_path / "rules.json"
    shutil.copy(ROOT / "data" / "rules.json", rules)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "RULES_PATH", str(rules))
    monkeypatch.setattr(config, "SERVICENOW_MOCK", True)  # list_queue devolve os incidentes fictícios
    from backend.db import init_db
    from backend.rules_engine import engine
    engine._mtime = None
    init_db()
    monkeypatch.setitem(sync._state, "novos_total", 0)
    monkeypatch.setitem(sync._state, "erro", None)
    from backend.main import app
    return TestClient(app)


def test_busca_a_fila_e_nao_repete(env):
    r1 = env.post("/sync").json()
    assert r1["erro"] is None and len(r1["novos"]) == 9 and r1["conhecidos"] == 0
    assert len(env.get("/incidents").json()) == 9  # já analisados, sem digitar número

    r2 = env.post("/sync").json()
    assert r2["novos"] == [] and r2["conhecidos"] == 9  # não reprocessa nem duplica histórico
    assert len(env.get("/history?acao=analise").json()) == 9


def test_ignora_o_que_nao_e_cftv(env, monkeypatch):
    fila = [
        {"sys_id": "a", "number": "INC1", "short_description": "RFID da empilhadeira sem leitura", "description": ""},
        {"sys_id": "b", "number": "INC2", "short_description": "Câmera PIR064 sem imagem", "description": ""},
    ]
    monkeypatch.setattr(sync.sn_api, "list_queue", lambda: fila)
    r = env.post("/sync").json()
    assert r["novos"] == ["INC2"] and [i["incident_number"] for i in r["ignorados"]] == ["INC1"]
    assert env.get("/incidents/INC1").status_code == 404


def test_sessao_expirada_vira_mensagem_clara(env, monkeypatch):
    def boom():
        raise SNAuthError("401")
    monkeypatch.setattr(sync.sn_api, "list_queue", boom)
    r = env.post("/sync").json()
    assert "Conectar" in r["erro"] and r["running"] is False

    monkeypatch.setattr("backend.routes.incidents.sn_api.get_incident", lambda n: (_ for _ in ()).throw(SNAuthError("401")))
    p = env.post("/incidents", json={"incident_number": "INC1"})
    assert p.status_code == 409 and "desconectado" in p.json()["detail"]


def test_agente_recupera_chamada_escrita_como_texto():
    from backend.agent import _text_tool_calls
    txt = 'Vou buscar.\n[\n {"tool_call_id": "2", "tool_name": "listar_fila", "parameters": {"texto": "Piracicaba", "estado": "Novo"}}\n]'
    calls = _text_tool_calls(txt)
    assert len(calls) == 1 and calls[0]["function"]["name"] == "listar_fila"
    assert '"Piracicaba"' in calls[0]["function"]["arguments"]
    assert _text_tool_calls("Nenhum incidente novo em Piracicaba.") == []
    assert _text_tool_calls('{"name": "apagar_tudo", "arguments": {}}') == []  # só ferramentas conhecidas

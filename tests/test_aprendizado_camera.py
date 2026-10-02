import shutil

import pytest
from fastapi.testclient import TestClient

from backend import db, digifort, learning, servidores
from backend.config import config, ROOT
from backend.routes import camera


@pytest.fixture()
def client(tmp_path, monkeypatch):
    rules = tmp_path / "rules.json"
    shutil.copy(ROOT / "data" / "rules.json", rules)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "RULES_PATH", str(rules))
    monkeypatch.setattr(config, "SERVICENOW_DRY_RUN", True)
    monkeypatch.setattr(config, "DIGIFORT_USER", "svc")
    monkeypatch.setattr(config, "DIGIFORT_PASSWORD", "x")
    monkeypatch.setattr(digifort, "CACHE_PATH", tmp_path / "c.json")
    monkeypatch.setattr(camera, "EVID", tmp_path / "evid")
    from backend.main import app
    from backend.rules_engine import engine
    engine._mtime = None
    db.init_db()
    return TestClient(app)


def _inc(n, cam, loc=None, conf=0, status="analisado", short="Câmeras sem conexão"):
    db.save_incident(n, {"sys_id": n.lower(), "short_description": short, "description": "", "camera_codigo": cam,
                         "localidade": loc, "localidade_confianca": conf}, status)


def test_prefixo():
    assert learning.prefixo("BM-LAM-CLI-048") == "BM" and learning.prefixo("PIR064") == "PIR"
    assert learning.prefixo("209") is None


def test_sugere_prefixo_novo_e_ignora_o_ja_coberto(client):
    _inc("INC1", "ZZQ-LOG-A-001", "Piracicaba", 85)
    _inc("INC2", "ZZQ-LOG-A-002", "Piracicaba", 100)
    _inc("INC3", "PIR-A-001", "Piracicaba", 100)  # PIR já tem regra
    _inc("INC4", "ZZQ-LOG-A-003")                  # sem destino: a regra nova resolveria
    s = learning.sugestoes()
    assert [x["prefixo"] for x in s] == ["ZZQ"]
    assert s[0]["localidade"] == "Piracicaba" and s[0]["resolveria_agora"] == 1 and s[0]["pode_criar"]


def test_nao_sugere_prefixo_misturado(client):
    _inc("INC1", "QQX-A-001", "Piracicaba", 100)
    _inc("INC2", "QQX-A-002", "João Monlevade", 100)
    assert learning.sugestoes() == []


def test_aceitar_cria_regra_e_reaplica_aos_sem_destino(client):
    _inc("INC1", "ZZQ-LOG-A-001", "Piracicaba", 85)
    _inc("INC2", "ZZQ-LOG-A-002", "Piracicaba", 100)
    _inc("INC4", "ZZQ-LOG-A-003")
    r = client.post("/rules/sugestoes/aceitar", json={"prefixo": "ZZQ", "localidade": "Piracicaba"})
    assert r.status_code == 201 and r.json()["reaplicados"] == ["INC4"]
    inc = db.get_incident("INC4")
    assert inc["localidade"] == "Piracicaba" and inc["grupo_display"] == "AMS-TI-CFTV-PIR"
    assert client.get("/rules/sugestoes").json() == []


def test_destinos_para_edicao_manual(client):
    d = client.get("/rules/destinos").json()
    assert any(x["localidade"] == "Piracicaba" and x["grupo"] for x in d)


def test_despacho_manual_de_incidente_sem_localidade(client, monkeypatch):
    _inc("INC9", "", None, 0)
    from backend.routes import incidents
    patch = {}
    monkeypatch.setattr(incidents.sn_api, "get_current", lambda sid: {"state": "1", "work_notes": ""})
    monkeypatch.setattr(incidents.sn_api, "patch_incident", lambda sid, f: patch.update(f) or True)
    assert client.post("/incidents/INC9/approve", json={}).status_code == 422  # sem destino: bloqueado
    dest = next(d for d in client.get("/rules/destinos").json() if d["localidade"] == "Piracicaba")
    r = client.post("/incidents/INC9/approve", json={"localidade": "Piracicaba", "grupo": dest["grupo"],
                                                      "grupo_display": dest["grupo_display"]})
    assert r.status_code == 200 and r.json()["editado"] is True
    assert patch["assignment_group"] == dest["grupo"] and patch["short_description"].startswith("Piracicaba - ")
    assert db.get_incident("INC9")["localidade"] == "Piracicaba"


def test_camera_de_incidente_em_andamento_le_do_servicenow(client, monkeypatch):
    sn = {"sys_id": "sysX", "short_description": "Barra Mansa - Câmera BM-PAT-A-058 sem conexão", "description": "",
          "state": "2", "assignment_group": "AMS-TI-CFTV-DBB", "u_incident_location": ""}
    monkeypatch.setattr(camera.sn_api, "get_incident", lambda n: sn)
    monkeypatch.setattr(camera.sn_api, "get_camera_code", lambda sid: "BM-PAT-A-058")
    srv = []
    monkeypatch.setattr(servidores, "cftv_da_unidade", lambda loc: srv.append(loc) or [{"nome": "S1", "ip": "10.0.0.1"}])
    digifort._inv.clear()
    monkeypatch.setattr(digifort, "inventario", lambda ip, forcar=False: {"ip": ip, "lido_em": "", "cameras": [
        {"nome": "BM-PAT-A-058", "descricao": "", "grupo": "", "active": True, "working": True, "inactive_s": 0}]})
    monkeypatch.setattr(digifort, "camera_state", lambda ip, n: {"working": True, "active": True, "inactive_s": 0, "active_s": 9})
    monkeypatch.setattr(digifort, "snapshot", lambda ip, n: b"\xff\xd8" + b"0" * 600)
    r = client.post("/incidents/INC7/camera/check").json()
    assert srv == ["Barra Mansa"]  # unidade veio do texto/regras (BM) ou do grupo AMS-TI-CFTV-DBB
    assert r["cameras"][0]["snapshot"] and r["incidente"]["estado"] == "2"


def test_unidade_desconhecida_pede_escolha(client, monkeypatch):
    sn = {"sys_id": "sysX", "short_description": "Câmeras sem conexão", "description": "", "state": "2",
          "assignment_group": "", "u_incident_location": ""}
    monkeypatch.setattr(camera.sn_api, "get_incident", lambda n: sn)
    monkeypatch.setattr(camera.sn_api, "get_camera_code", lambda sid: "XX-A-001")
    r = client.post("/incidents/INC7/camera/check")
    assert r.status_code == 422 and "escolha a localidade" in r.json()["detail"]


def test_nota_de_encerramento_exige_print_anexado_e_nao_repete(client, monkeypatch):
    monkeypatch.setattr(config, "SERVICENOW_DRY_RUN", False)  # valida a trava de verdade
    _inc("INC1", "BM-LAM-CLI-048", "Barra Mansa", 100, short="Barra Mansa - Câmera BM-LAM-CLI-048 sem conexão")
    camera.EVID.mkdir(parents=True, exist_ok=True)
    camera._file("INC1", "BM-LAM-CLI-048").write_bytes(b"x" * 600)
    anexos, notas = [], []
    monkeypatch.setattr(camera.sn_api, "list_attachment_names", lambda sid: list(anexos))
    monkeypatch.setattr(camera.sn_api, "get_current", lambda sid: {"state": "2", "work_notes": "\n".join(notas)})
    monkeypatch.setattr(camera.sn_api, "patch_incident", lambda sid, f: notas.append(f["work_notes"]) or True)
    txt = client.get("/incidents/INC1/camera/closing-draft").json()["texto"]
    assert "Câmera BM-LAM-CLI-048 testada" in txt and txt.startswith("Causa base:")
    assert client.post("/incidents/INC1/camera/closing-note", json={"texto": txt}).status_code == 409  # sem anexo
    anexos.append(camera._file("INC1", "BM-LAM-CLI-048").name)
    assert client.post("/incidents/INC1/camera/closing-note", json={"texto": txt}).json()["status"] == "registrada"
    assert client.post("/incidents/INC1/camera/closing-note", json={"texto": txt}).json()["status"] == "já registrada"
    assert len(notas) == 1


def test_formatos_de_codigo_no_campo():
    from backend.payload import build_title, field_codes
    assert field_codes("03-SUC") == ["03-SUC"]
    assert field_codes("08-suc") == ["08-SUC"]
    assert field_codes("209 e 177") == ["209", "177"]
    assert field_codes("camera da MR4") == []
    assert build_title("Barra Mansa", "[CFTV] - Câmeras sem conexão", "", False, "12-SUC") == ("Barra Mansa - Câmera 12-SUC sem conexão", True)
    assert build_title("Monlevade", "[CFTV] - Câmeras sem conexão", "", False, "209 e 177") == ("Monlevade - Câmeras 209/177 sem conexão", True)


def test_campo_localidade_sem_acento_e_com_prefixo():
    from backend.rules_engine import engine
    base = {"short_description": "[CFTV] - Imagem degradada", "description": "Imagem alterada", "camera_codigo": ""}
    assert engine.apply_rules({**base, "u_incident_location": "Sabara"})["localidade"] == "Sabará"
    assert engine.apply_rules({**base, "u_incident_location": "CFTV - Monlevade"})["localidade"] == "João Monlevade"

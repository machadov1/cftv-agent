"""Despacho que usa o resultado dos testes feitos antes (ping SCOM, câmera) e impacto/urgência no /approve."""
import shutil
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend import scom
from backend.config import config, ROOT
from backend.models import ApproveIn
from backend.payload import build_first_touch

ALERTA = ("Servidor nao esta comunicando com SCOM server - The System Center Management Health Service on computer "
          "IRA-APP-CFTV02.Americas.mittalco.com failed to heartbeat.")
SAIDA = ("Disparando IRA-APP-CFTV02.Americas.mittalco.com [10.58.40.12] com 32 bytes de dados:\n"
         + "Resposta de 10.58.40.12: bytes=32 tempo=3ms TTL=125\n" * 10
         + "Pacotes: Enviados = 10, Recebidos = 10, Perdidos = 0 (0% de perda)")
PING_OK = {"host": "IRA-APP-CFTV02", "target": "IRA-APP-CFTV02.Americas.mittalco.com", "ip": "10.58.40.12",
           "perda_percentual": 0, "ok": True, "resolveu": True, "saida": SAIDA}
VAL = {"host": "IRA-APP-CFTV02", "perda": "0", "hora": "15:47", "arquivo": None}


def _alerta():
    return {"short_description": ALERTA, "description": ALERTA, "localidade": "Iracemápolis"}


def test_imagem_desenhada_da_saida_real(tmp_path, monkeypatch):
    monkeypatch.setattr(scom, "EVIDENCE_DIR", tmp_path)
    out = scom.render_evidence("IRA-APP-CFTV02", PING_OK, "INC1")
    assert out.name == "ping_INC1_IRA-APP-CFTV02.png" and out.read_bytes()[:4] == b"\x89PNG"
    from PIL import Image
    w, h = Image.open(out).size
    assert w >= 760 and h > 21 * 12  # cabeçalho + as 13 linhas da saída


def test_nota_scom_so_com_validacao_recente():
    inc = _alerta()
    f, w = build_first_touch(inc, {**inc, "grupo": "g"}, {"state": "1", "work_notes": ""}, {"scom": VAL})
    assert f["work_notes"] == scom.WORK_NOTE.format(host="IRA-APP-CFTV02")
    assert any("validação SCOM" in x for x in w) and "short_description" not in f
    f, _ = build_first_touch(inc, {**inc, "grupo": "g"}, {"state": "1", "work_notes": ""}, {"scom": None})
    assert f["work_notes"] == "Encaminhado para equipe."


def test_camera_testada_e_editada_e_severidade():
    from backend.servicenow_mock import MOCK_INCIDENTS
    inc = MOCK_INCIDENTS["INC9000001"]
    final = {"localidade": "Piracicaba", "grupo": "g"}
    cam = {"codigos": ["PIR064"], "hora": "15:40"}
    f, _ = build_first_touch(inc, final, None, {"camera": cam})
    assert f["work_notes"] == ("Encaminhado para equipe. Teste da câmera PIR064 às 15:40: imagem normalizada no Digifort, "
                               "print anexado.")
    f, _ = build_first_touch(inc, {**final, "work_notes": "Texto meu."}, None, {"camera": cam})
    assert f["work_notes"] == "Texto meu."  # editada vence
    f, _ = build_first_touch(inc, {**final, "impact": "4", "urgency": "4"}, None)
    assert (f["impact"], f["urgency"]) == ("4", "4")
    assert f["work_notes"].startswith("Encaminhado para equipe.\n\nIncidente em verificação")
    # nota padrão já existe: só a linha de severidade vai
    f, _ = build_first_touch(inc, {**final, "impact": "4"}, {"state": "1", "work_notes": "Encaminhado para equipe."})
    assert f["work_notes"].startswith("Incidente em verificação") and "impacto alterado para 4" in f["work_notes"]


def test_approve_in_impacto_urgencia():
    assert ApproveIn(impact="4", urgency="3").impact == "4"
    with pytest.raises(ValidationError):
        ApproveIn(impact="5")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    rules = tmp_path / "rules.json"
    shutil.copy(ROOT / "data" / "rules.json", rules)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "RULES_PATH", str(rules))
    monkeypatch.setattr(config, "SERVICENOW_DRY_RUN", True)
    monkeypatch.setattr(scom, "EVIDENCE_DIR", tmp_path / "evid")
    from backend import servidores
    monkeypatch.setattr(servidores, "find", lambda h: None)
    monkeypatch.setattr(scom, "run_ping", lambda host, domain=scom.DOMAIN, count=10, target=None: dict(PING_OK))

    from backend.main import app
    from backend.db import init_db
    from backend.rules_engine import engine
    engine._mtime = None
    init_db()
    from backend.routes import incidents
    fake = {"sys_id": "abc123", "number": "INC1", "short_description": ALERTA, "description": ALERTA}
    estado = {"state": "1", "work_notes": "", "anexos": [], "patches": []}
    monkeypatch.setattr(incidents.sn_api, "get_incident", lambda n: fake)
    monkeypatch.setattr(incidents.sn_api, "get_current", lambda sid: {"state": estado["state"], "work_notes": estado["work_notes"]})
    monkeypatch.setattr(incidents.sn_api, "list_attachment_names", lambda sid: list(estado["anexos"]))

    def attach(sid, nome, data, ct="image/jpeg"):
        estado["anexos"].append(nome)
        return True

    def patch(sid, fields):
        estado["patches"].append(fields)
        estado["state"] = fields.get("state", estado["state"])
        estado["work_notes"] += fields.get("work_notes", "")
        return True
    monkeypatch.setattr(incidents.sn_api, "attach_file", attach)
    monkeypatch.setattr(incidents.sn_api, "patch_incident", patch)
    c = TestClient(app)
    c.estado = estado
    return c


def test_despacho_scom_anexa_e_posta_validacao(client):
    client.post("/incidents", json={"incident_number": "INC1"})
    # sem ping: nota padrão, nada anexado
    p = client.get("/incidents/INC1/payload").json()
    assert p["fields"]["work_notes"] == "Encaminhado para equipe." and p["anexo"] is None
    r = client.post("/incidents/INC1/ping").json()
    assert r["ok"] and r["evidencia"] == "ping_INC1_IRA-APP-CFTV02.png"
    assert client.get("/incidents/INC1/ping/evidencia").headers["content-type"] == "image/png"
    p = client.get("/incidents/INC1/payload").json()
    assert p["fields"]["work_notes"].startswith("Causa base") and p["anexo"] == "ping_INC1_IRA-APP-CFTV02.png"
    r = client.post("/incidents/INC1/approve", json={"impact": "4", "urgency": "4"}).json()
    assert r["anexo"] == "anexado" and client.estado["anexos"] == ["ping_INC1_IRA-APP-CFTV02.png"]
    enviado = client.estado["patches"][-1]
    assert enviado["work_notes"].startswith("Causa base") and "impacto alterado para 4" in enviado["work_notes"]
    assert (enviado["impact"], enviado["state"]) == ("4", "2")
    # já despachado: registrar não duplica anexo nem nota
    r = client.post("/incidents/INC1/ping/registrar").json()
    assert r["status"] == "já registrada" and client.estado["anexos"] == ["ping_INC1_IRA-APP-CFTV02.png"]


def test_registrar_validacao_em_scom_ja_despachado(client):
    client.post("/incidents", json={"incident_number": "INC1"})
    client.estado.update(state="2", work_notes="Encaminhado para equipe.")
    assert client.post("/incidents/INC1/ping/registrar").status_code == 409  # sem ping recente
    client.post("/incidents/INC1/ping")
    r = client.post("/incidents/INC1/ping/registrar").json()
    assert r["status"] == "registrada" and r["anexo"] == "anexado"
    assert client.estado["patches"][-1] == {"work_notes": scom.WORK_NOTE.format(host="IRA-APP-CFTV02")}
    assert client.post("/incidents/INC1/ping/registrar").json()["status"] == "já registrada"


def test_validacao_vencida_ou_ping_falho_nao_vale(client, monkeypatch):
    client.post("/incidents", json={"incident_number": "INC1"})
    client.post("/incidents/INC1/ping")
    assert scom.ultima_validacao("INC1")
    assert scom.ultima_validacao("INC1", datetime.now(timezone.utc) + timedelta(minutes=31)) is None
    monkeypatch.setattr(scom, "run_ping", lambda *a, **k: {**PING_OK, "ok": False, "perda_percentual": 40})
    client.post("/incidents/INC1/ping")
    assert scom.ultima_validacao("INC1") is None  # o último teste é o que vale

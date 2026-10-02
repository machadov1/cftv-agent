import shutil

import pytest
from fastapi.testclient import TestClient

from backend import digifort, servidores
from backend.config import config, ROOT

SRV = [{"nome": "BMA-APP-CFTV01", "ip": "10.0.0.1"}, {"nome": "BMA-APP-CFTV03", "ip": "10.0.0.3"}]


@pytest.fixture()
def dg(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DIGIFORT_USER", "svc")
    monkeypatch.setattr(config, "DIGIFORT_PASSWORD", "x")
    monkeypatch.setattr(digifort, "CACHE_PATH", tmp_path / "cache.json")


def test_parse_text():
    kv = digifort.parse_text("RESPONSE_CODE=0\nCAMERA_0_NAME = BM-LAM-CLI-048\nlixo sem chave\n")
    assert kv["CAMERA_0_NAME"] == "BM-LAM-CLI-048" and kv["RESPONSE_CODE"] == "0"


def test_locate_exato_no_segundo_servidor_e_lembra(dg, monkeypatch):
    chamadas = []

    def fake(ip, mask):
        chamadas.append((ip, mask))
        return ["bm-lam-cli-048"] if ip == "10.0.0.3" else []
    monkeypatch.setattr(digifort, "list_cameras", fake)
    r = digifort.locate("BM-LAM-CLI-048", SRV)
    assert r["achada"]["ip"] == "10.0.0.3" and r["achada"]["nome"] == "bm-lam-cli-048"
    chamadas.clear()
    digifort.locate("BM-LAM-CLI-048", SRV)
    assert chamadas[0][0] == "10.0.0.3"  # servidor já conhecido vai na frente


def test_locate_ambigua_nao_escolhe(dg, monkeypatch):
    monkeypatch.setattr(digifort, "list_cameras", lambda ip, mask: [f"BM-LAM-CLI-048-{ip[-1]}"])
    r = digifort.locate("BM-LAM-CLI-048", SRV)
    assert r["achada"] is None and len(r["candidatas"]) == 2


def test_locate_servidor_fora_nao_derruba(dg, monkeypatch):
    def fake(ip, mask):
        if ip == "10.0.0.1":
            raise digifort.DigifortError("sem resposta")
        return ["BM-LAM-CLI-048"]
    monkeypatch.setattr(digifort, "list_cameras", fake)
    r = digifort.locate("BM-LAM-CLI-048", SRV)
    assert r["achada"]["ip"] == "10.0.0.3" and len(r["erros"]) == 1


def test_sem_credencial(monkeypatch):
    monkeypatch.setattr(config, "DIGIFORT_USER", "")
    with pytest.raises(digifort.DigifortError):
        digifort.list_cameras("10.0.0.1", "x")


@pytest.fixture()
def client(tmp_path, monkeypatch, dg):
    rules = tmp_path / "rules.json"
    shutil.copy(ROOT / "data" / "rules.json", rules)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "RULES_PATH", str(rules))
    monkeypatch.setattr(config, "SERVICENOW_DRY_RUN", True)
    from backend.main import app
    from backend.db import init_db, save_incident
    from backend.routes import camera
    init_db()
    monkeypatch.setattr(camera, "EVID", tmp_path / "evid")
    monkeypatch.setattr(servidores, "cftv_da_unidade", lambda loc: SRV)
    save_incident("INC1", {"sys_id": "abc", "short_description": "x", "localidade": "Barra Mansa",
                           "grupo": "g", "camera_codigo": "BM-LAM-CLI-048"})
    save_incident("INC2", {"sys_id": "def", "short_description": "x", "localidade": "Barra Mansa",
                           "grupo": "g", "camera_codigo": "camera da MR4"})
    return TestClient(app)


def test_check_volta_e_gera_snapshot_depois_anexa_uma_vez(client, monkeypatch):
    monkeypatch.setattr(digifort, "list_cameras", lambda ip, mask: ["BM-LAM-CLI-048"])
    monkeypatch.setattr(digifort, "camera_state", lambda ip, n: {"working": True, "active": True, "inactive_s": 0, "active_s": 50})
    monkeypatch.setattr(digifort, "snapshot", lambda ip, n: b"\xff\xd8" + b"0" * 600)
    r = client.post("/incidents/INC1/camera/check")
    cam = r.json()["cameras"][0]
    assert r.status_code == 200 and cam["snapshot"] and cam["achada"]["servidor"] == "BMA-APP-CFTV01"
    assert client.get("/incidents/INC1/camera/snapshot/BM-LAM-CLI-048").status_code == 200

    from backend.routes import camera
    anexos, enviados = [], []
    monkeypatch.setattr(camera.sn_api, "list_attachment_names", lambda sid: list(anexos))
    monkeypatch.setattr(camera.sn_api, "attach_file", lambda sid, nome, dados: enviados.append(nome) or True)
    a = client.post("/incidents/INC1/camera/attach").json()
    assert a["resultado"][0]["status"] == "anexado" and a["dry_run"] is True
    anexos.extend(enviados)
    b = client.post("/incidents/INC1/camera/attach").json()
    assert b["resultado"][0]["status"] == "já anexado" and len(enviados) == 1


def test_camera_ainda_fora_nao_gera_snapshot(client, monkeypatch):
    monkeypatch.setattr(digifort, "list_cameras", lambda ip, mask: ["BM-LAM-CLI-048"])
    monkeypatch.setattr(digifort, "camera_state", lambda ip, n: {"working": False, "active": True, "inactive_s": 900, "active_s": 0})
    monkeypatch.setattr(digifort, "snapshot", lambda ip, n: pytest.fail("não deveria tirar snapshot"))
    cam = client.post("/incidents/INC1/camera/check").json()["cameras"][0]
    assert not cam["snapshot"] and cam["inactive_s"] == 900 and "sem sinal" in cam["erro"]
    assert client.post("/incidents/INC1/camera/attach").status_code == 422


def test_codigo_em_texto_livre_e_recusado(client):
    assert client.post("/incidents/INC2/camera/check").status_code == 422


def test_camera_desativada_tem_mensagem_propria(client, monkeypatch):
    monkeypatch.setattr(digifort, "list_cameras", lambda ip, mask: ["BM-LAM-CLI-048"])
    monkeypatch.setattr(digifort, "camera_state", lambda ip, n: {"working": False, "active": False, "inactive_s": 0, "active_s": 0})
    cam = client.post("/incidents/INC1/camera/check").json()["cameras"][0]
    assert not cam["snapshot"] and "DESATIVADA" in cam["erro"]


def test_motivo_xml():
    assert digifort._motivo("<Response><Code>4</Code><Message>Object deactivated</Message></Response>") == "4 Object deactivated"


def test_server_time_e_faixa_com_hora_do_servidor(dg, monkeypatch):
    import io
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (1280, 720), (90, 90, 90)).save(buf, "JPEG"); jpeg = buf.getvalue()

    class R:
        status_code = 200
        text = "RESPONSE_CODE=0\nDATETIME=2026-09-30 15:02:24.374\n"
        headers = {"Content-Type": "image/jpeg"}
        content = jpeg
    monkeypatch.setattr(digifort, "_get", lambda ip, path, params=None: R())
    assert digifort.server_time("10.0.0.1") == "30/09/2026 15:02:24"
    img = Image.open(io.BytesIO(digifort.snapshot("10.0.0.1", "CAM")))
    assert img.width == 1280 and img.height > 720          # faixa acrescentada, vídeo intacto
    assert img.getpixel((640, 100)) == pytest.approx((90, 90, 90), abs=6)
    faixa = img.crop((0, 720, img.width, img.height)).convert("L")
    assert sum(1 for v in faixa.getdata() if v > 200) > 100  # texto branco na faixa


def test_credencial_por_servidor_sobrepoe_a_padrao(dg, monkeypatch, tmp_path):
    arq = tmp_path / "cred.json"
    arq.write_text('{"10.0.0.9": {"usuario": "outro", "senha": "s3"}}', encoding="utf-8")
    monkeypatch.setattr(digifort, "CRED_PATH", arq)
    assert digifort._cred("10.0.0.9") == ("outro", "s3")
    assert digifort._cred("10.0.0.1") == ("svc", "x")          # sem entrada: conta padrão do .env
    monkeypatch.setattr(digifort, "CRED_PATH", tmp_path / "nao_existe.json")
    assert digifort._cred("10.0.0.9") == ("svc", "x")

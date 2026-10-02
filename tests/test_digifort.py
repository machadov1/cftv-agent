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
    digifort._inv.clear()


def mk(nome, descricao="", active=True, working=True):
    return {"nome": nome, "descricao": descricao, "grupo": "", "active": active, "working": working, "inactive_s": 0}


def inv(por_ip, chamadas=None):
    """Dublê de digifort.inventario: {ip: [câmeras]} ou {ip: DigifortError}."""
    def fake(ip, forcar=False):
        if chamadas is not None:
            chamadas.append(ip)
        v = por_ip.get(ip, [])
        if isinstance(v, Exception):
            raise v
        return {"ip": ip, "lido_em": "02/10 10:00", "cameras": v}
    return fake


def test_parse_text():
    kv = digifort.parse_text("RESPONSE_CODE=0\nCAMERA_0_NAME = BM-LAM-CLI-048\nlixo sem chave\n")
    assert kv["CAMERA_0_NAME"] == "BM-LAM-CLI-048" and kv["RESPONSE_CODE"] == "0"


def test_locate_exato_no_segundo_servidor_e_lembra(dg, monkeypatch):
    chamadas = []
    monkeypatch.setattr(digifort, "inventario", inv({"10.0.0.3": [mk("bm-lam-cli-048")]}, chamadas))
    r = digifort.locate("BM-LAM-CLI-048", SRV)
    assert r["achada"]["ip"] == "10.0.0.3" and r["achada"]["nome"] == "bm-lam-cli-048"
    chamadas.clear()
    digifort.locate("BM-LAM-CLI-048", SRV)
    assert chamadas == ["10.0.0.3"]  # já confirmada: vai direto ao servidor conhecido e para


def test_locate_ambigua_nao_escolhe(dg, monkeypatch):
    monkeypatch.setattr(digifort, "inventario", inv({"10.0.0.1": [mk("BM-LAM-CLI-048-1")], "10.0.0.3": [mk("BM-LAM-CLI-048-3")]}))
    r = digifort.locate("BM-LAM-CLI-048", SRV)
    assert r["achada"] is None and len(r["candidatas"]) == 2


def test_locate_servidor_fora_nao_derruba(dg, monkeypatch):
    monkeypatch.setattr(digifort, "inventario", inv({"10.0.0.1": digifort.DigifortError("sem resposta", "rede"),
                                                     "10.0.0.3": [mk("BM-LAM-CLI-048")]}))
    r = digifort.locate("BM-LAM-CLI-048", SRV)
    assert r["achada"]["ip"] == "10.0.0.3" and len(r["erros"]) == 1


@pytest.mark.parametrize("consulta, esperado, minimo", [
    ("MDE 11", "MDE-011", 100),          # separador e zero à esquerda
    ("mde_011", "MDE-011", 100),
    ("BM 48", "BM-LAM-CLI-048", 90),      # prefixo + número
    ("209", "PIR-PORT-209", 90),          # só o número
    ("câmera da portaria", "PIR-PORT-209", 50),  # palavra da descrição
    ("balança", "PIR-BAL-010", 50),
])
def test_candidatas_tolerantes(consulta, esperado, minimo):
    cams = [mk("BM-LAM-CLI-048", "Laminação cliente"), mk("PIR-PORT-209", "Portaria principal"), mk("MDE-011"),
            mk("PIR-BAL-010", "Balança rodoviária")]
    top = digifort.candidatas(consulta, cams)
    assert top and top[0]["nome"] == esperado and top[0]["pontos"] >= minimo


def test_candidatas_sem_semelhanca_e_limite():
    cams = [mk(f"PIR-CAM-{i:03d}") for i in range(20)]
    assert digifort.candidatas("xyz", cams) == []
    assert len(digifort.candidatas("PIR CAM", cams)) == 5


def test_locate_uma_candidata_forte_escolhe_sozinha_e_texto_livre_nao(dg, monkeypatch):
    monkeypatch.setattr(digifort, "inventario", inv({"10.0.0.1": [mk("BM-LAM-CLI-048"), mk("BM-PORT-001", "Portaria")]}))
    assert digifort.locate("BM 48", SRV)["achada"]["nome"] == "BM-LAM-CLI-048"
    livre = digifort.locate("camera da portaria", SRV, automatico=False)
    assert livre["achada"] is None and livre["candidatas"][0]["nome"] == "BM-PORT-001"


def test_inventario_junta_cameras_e_estado_e_usa_cache(dg, monkeypatch):
    chamadas = []

    class R:
        status_code = 200

        def __init__(self, text):
            self.text = text

    def fake_get(ip, path, params=None):
        chamadas.append(path)
        if path == "Cameras/GetCameras":
            return R("RESPONSE_CODE=0\nCOUNT=2\nCAMERA_0_NAME=BM-001\nCAMERA_0_DESCRIPTION=Portaria\nCAMERA_0_ACTIVE=TRUE\n"
                     "CAMERA_1_NAME=BM-002\nCAMERA_1_ACTIVE=FALSE\n")
        return R("RESPONSE_CODE=0\nCAMERA_0_NAME=BM-001\nCAMERA_0_WORKING=FALSE\nCAMERA_0_INACTIVETIME=120\n")
    monkeypatch.setattr(digifort, "_get", fake_get)
    r = digifort.inventario("10.0.0.1")
    c1, c2 = r["cameras"]
    assert (c1["nome"], c1["descricao"], c1["working"], c1["inactive_s"]) == ("BM-001", "Portaria", False, 120)
    assert c2["active"] is False and c2["working"] is None
    digifort.inventario("10.0.0.1")
    assert len(chamadas) == 2  # segunda leitura veio do cache
    digifort.inventario("10.0.0.1", forcar=True)
    assert len(chamadas) == 4


def test_inventario_api_antiga_refaz_so_com_nome(dg, monkeypatch):
    pedidos = []

    class R:
        status_code = 200

        def __init__(self, text):
            self.text = text

    def fake_get(ip, path, params=None):
        pedidos.append(params.get("Fields"))
        if path == "Cameras/GetCameras" and params["Fields"] != "Name":
            return R("RESPONSE_CODE=6\nRESPONSE_MESSAGE=Invalid field\n")
        return R("RESPONSE_CODE=0\nCAMERA_0_NAME=BM-001\n")
    monkeypatch.setattr(digifort, "_get", fake_get)
    assert digifort.inventario("10.0.0.1")["cameras"][0]["nome"] == "BM-001"
    assert pedidos[1] == "Name"


def test_erro_tem_tipo(dg, monkeypatch):
    import requests

    class R:
        status_code = 401
        text = ""
        content = b""
    monkeypatch.setattr(digifort.requests, "get", lambda *a, **k: R())
    with pytest.raises(digifort.DigifortError) as e:
        digifort.inventario("10.0.0.1")
    assert e.value.tipo == "credencial"

    def porta(*a, **k):
        raise requests.exceptions.ConnectTimeout()
    monkeypatch.setattr(digifort.requests, "get", porta)
    with pytest.raises(digifort.DigifortError) as e:
        digifort.inventario("10.0.0.2")
    assert e.value.tipo == "timeout" and "não atendeu" in str(e.value)

    def lento(*a, **k):
        raise requests.exceptions.ReadTimeout()
    monkeypatch.setattr(digifort.requests, "get", lento)
    with pytest.raises(digifort.DigifortError) as e:
        digifort.inventario("10.0.0.4")
    assert e.value.tipo == "lento" and "conectou" in str(e.value) and "porta" not in str(e.value)


def test_snapshot_espera_mais_que_as_consultas(dg, monkeypatch):
    usados = []

    class R:
        status_code = 200
        headers = {"Content-Type": "text/plain"}
        content = b""
        text = "RESPONSE_CODE=0"

    def fake(url, params=None, auth=None, timeout=None):
        usados.append(timeout[1])
        return R()
    monkeypatch.setattr(digifort.requests, "get", fake)
    with pytest.raises(digifort.DigifortError):
        digifort.snapshot("10.0.0.1", "CAM")
    assert usados[0] == digifort.SNAPSHOT_TIMEOUT


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
    monkeypatch.setattr(digifort, "inventario", inv({"10.0.0.1": [mk("BM-LAM-CLI-048")]}))
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
    monkeypatch.setattr(digifort, "inventario", inv({"10.0.0.1": [mk("BM-LAM-CLI-048")]}))
    monkeypatch.setattr(digifort, "camera_state", lambda ip, n: {"working": False, "active": True, "inactive_s": 900, "active_s": 0})
    monkeypatch.setattr(digifort, "snapshot", lambda ip, n: pytest.fail("não deveria tirar snapshot"))
    cam = client.post("/incidents/INC1/camera/check").json()["cameras"][0]
    assert not cam["snapshot"] and cam["inactive_s"] == 900 and "sem sinal" in cam["erro"]
    assert client.post("/incidents/INC1/camera/attach").status_code == 422


def test_texto_livre_sugere_candidatas_e_escolha_e_lembrada(client, monkeypatch):
    monkeypatch.setattr(digifort, "inventario", inv({"10.0.0.1": [mk("BM-MR4-001", "Moinho MR4"), mk("BM-PORT-001")]}))
    monkeypatch.setattr(digifort, "camera_state", lambda ip, n: {"working": True, "active": True, "inactive_s": 0, "active_s": 9})
    monkeypatch.setattr(digifort, "snapshot", lambda ip, n: b"\xff\xd8" + b"0" * 600)
    r = client.post("/incidents/INC2/camera/check").json()["cameras"][0]
    assert r["achada"] is None and r["texto_livre"] and r["candidatas"][0]["nome"] == "BM-MR4-001"

    escolha = {"consulta": "camera da MR4", "ip": "10.0.0.1", "nome": "BM-MR4-001"}
    r = client.post("/incidents/INC2/camera/check", json={"escolha": escolha}).json()["cameras"][0]
    assert r["snapshot"] and r["codigo"] == "BM-MR4-001" and not r["texto_livre"]
    # da próxima vez o incidente já usa a câmera confirmada, sem perguntar
    r = client.post("/incidents/INC2/camera/check").json()["cameras"][0]
    assert r["achada"]["nome"] == "BM-MR4-001" and r["snapshot"]
    assert client.get("/incidents/INC2/camera/closing-draft").json()["texto"].count("BM-MR4-001") == 1


def test_escolha_de_outra_unidade_e_recusada(client):
    escolha = {"consulta": "BM-LAM-CLI-048", "ip": "10.9.9.9", "nome": "X"}
    assert client.post("/incidents/INC1/camera/check", json={"escolha": escolha}).status_code == 422


def test_camera_desativada_tem_mensagem_propria(client, monkeypatch):
    monkeypatch.setattr(digifort, "inventario", inv({"10.0.0.1": [mk("BM-LAM-CLI-048")]}))
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
    monkeypatch.setattr(digifort, "_get", lambda ip, path, params=None, leitura=None: R())
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


def test_mesma_camera_no_reserva_desativada_escolhe_a_ativa(dg, monkeypatch):
    monkeypatch.setattr(digifort, "inventario", inv({"10.0.0.1": [mk("BM-ACI-H-001", active=False, working=None)],
                                                     "10.0.0.3": [mk("BM-ACI-H-001")]}))
    r = digifort.locate("BM-ACI-H-001", SRV)
    assert r["achada"]["ip"] == "10.0.0.3"


def test_lembrada_no_reserva_desativada_e_reaprendida(dg, monkeypatch):
    digifort.lembrar("BM-PAT-A-058", {"servidor": "BMA-APP-CFTV01", "ip": "10.0.0.1", "nome": "BM-PAT-A-058"})
    monkeypatch.setattr(digifort, "inventario", inv({"10.0.0.1": [mk("BM-PAT-A-058", active=False, working=None)],
                                                     "10.0.0.3": [mk("BM-PAT-A-058")]}))
    assert digifort.locate("BM-PAT-A-058", SRV)["achada"]["ip"] == "10.0.0.3"
    assert digifort.lembrada("BM-PAT-A-058")["ip"] == "10.0.0.3"


def test_encerrar_pela_tela_de_camera(client, monkeypatch):
    from backend.routes import camera
    texto = "Causa base: Câmera sem comunicação.\nDescrição: Câmera BM-LAM-CLI-048 testada. Incidente encerrado."
    assert client.post("/incidents/INC1/camera/close", json={"texto": texto}).status_code == 422  # sem print ainda

    monkeypatch.setattr(digifort, "inventario", inv({"10.0.0.1": [mk("BM-LAM-CLI-048")]}))
    monkeypatch.setattr(digifort, "camera_state", lambda ip, n: {"working": True, "active": True, "inactive_s": 0, "active_s": 9})
    monkeypatch.setattr(digifort, "snapshot", lambda ip, n: b"\xff\xd8" + b"0" * 600)
    client.post("/incidents/INC1/camera/check")

    enviados, estado = [], {"state": "2", "work_notes": ""}
    monkeypatch.setattr(camera.sn_api, "list_attachment_names", lambda sid: [])
    monkeypatch.setattr(camera.sn_api, "get_current", lambda sid: dict(estado))
    monkeypatch.setattr(camera.sn_api, "patch_incident", lambda sid, f: enviados.append(f) or True)
    r = client.post("/incidents/INC1/camera/close", json={"texto": texto}).json()
    assert r["status"] == "encerrado" and r["dry_run"] is True
    assert enviados[0]["state"] == "6" and enviados[0]["close_code"] == "Solved" and enviados[0]["close_notes"] == texto
    assert enviados[0]["work_notes"] == texto

    estado.update(state="6")
    assert client.post("/incidents/INC1/camera/close", json={"texto": texto}).json()["status"] == "já encerrado"
    assert len(enviados) == 1


def test_encerrar_nao_repete_work_note_ja_registrada(client, monkeypatch):
    from backend.routes import camera
    texto = "Causa base: Câmera sem comunicação.\nDescrição: Câmera BM-LAM-CLI-048 testada. Incidente encerrado."
    monkeypatch.setattr(digifort, "inventario", inv({"10.0.0.1": [mk("BM-LAM-CLI-048")]}))
    monkeypatch.setattr(digifort, "camera_state", lambda ip, n: {"working": True, "active": True, "inactive_s": 0, "active_s": 9})
    monkeypatch.setattr(digifort, "snapshot", lambda ip, n: b"\xff\xd8" + b"0" * 600)
    client.post("/incidents/INC1/camera/check")
    enviados = []
    monkeypatch.setattr(camera.sn_api, "list_attachment_names", lambda sid: [])
    monkeypatch.setattr(camera.sn_api, "get_current", lambda sid: {"state": "2", "work_notes": "02/10 - Victor\n" + texto})
    monkeypatch.setattr(camera.sn_api, "patch_incident", lambda sid, f: enviados.append(f) or True)
    client.post("/incidents/INC1/camera/close", json={"texto": texto})
    assert "work_notes" not in enviados[0] and enviados[0]["close_notes"] == texto

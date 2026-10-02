"""Código da câmera pelo rótulo do formulário, releitura dos pendentes, RITM pelo catálogo e pedido de acesso (LGPD)."""
import shutil

import pytest
from fastapi.testclient import TestClient

from backend import db, ritm, teams
from backend.config import config, ROOT
from backend.payload import build_first_touch, field_codes, is_access_request, WORK_NOTE_ACESSO
from backend.servicenow_api import camera_code_from_form


def _form(var_id: str, label: str, value: str) -> str:
    return (f'<input id="incident.short_description"><label for="ni.QS{var_id}"><span>&nbsp; {label}</span></label>'
            f'<input type="text" id="ni.QS{var_id}" value="{value}">')


def test_codigo_pelo_rotulo_em_qualquer_formulario():
    assert camera_code_from_form(_form("4436e00d1b315510e8142f07b04bcb0d", "Câmera (Número do Objeto):", "06-SUC")) == "06-SUC"
    assert camera_code_from_form(_form("0123456789abcdef0123456789abcdef", "Câmeras sem conexão (Número do Objeto):",
                                       "BM-PAT-G-052")) == "BM-PAT-G-052"
    assert camera_code_from_form(_form("0123456789abcdef0123456789abcdef", "Área", "metalicos")) == ""


def test_campo_com_prefixo_herdado_e_frase():
    assert field_codes("MDE 011, 001, 002") == ["MDE-011", "MDE-001", "MDE-002"]
    assert field_codes("Câmeras sem conexão RES027 RES028 RES029 RES030 e RES031") == \
        ["RES027", "RES028", "RES029", "RES030", "RES031"]
    assert field_codes("399, 407, 411, 412, 393, 71, 72 394") == ["399", "407", "411", "412", "393", "71", "72", "394"]


def test_numeracao_do_mosaico_na_descricao_sem_campo():
    from backend.payload import camera_codes
    desc = ("** PARA DIRECIONAMENTO, PRENCHER O IC ... LCB - SRV-CFTV-PIR01 **\n\n"
            "Descrição do problema: Usuário relata que a câmera esta sem imagem\n\n"
            "Nome do ponto de imagem (nome da câmera que aparece no mosaico): 399, 407, 411, 412, 393, 71, 72 394\n"
            "Código do equipamento: AA42893\n")
    assert camera_codes(None, "[BR-SD] CFTV LONGOS - PROBLEMAS EM GERAL", desc) == \
        ["399", "407", "411", "412", "393", "71", "72", "394"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    rules = tmp_path / "rules.json"
    shutil.copy(ROOT / "data" / "rules.json", rules)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "RULES_PATH", str(rules))
    monkeypatch.setattr(config, "SERVICENOW_DRY_RUN", True)
    monkeypatch.setattr(config, "SERVICENOW_MOCK", True)
    monkeypatch.setattr(ritm, "_MOCK_RITMS", [])
    from backend.main import app
    from backend.db import init_db
    from backend.rules_engine import engine
    engine._mtime = None
    init_db()
    return TestClient(app)


def test_vazio_nao_apaga_codigo_e_reler_atualiza_titulo(client, monkeypatch):
    from backend import analysis
    from backend.routes import incidents
    sn = {"sys_id": "s1", "short_description": "[CFTV] - Imagem degradada", "description": "Usina: Barra Mansa",
          "u_incident_location": "CFTV - Barra Mansa"}
    monkeypatch.setattr(incidents.sn_api, "get_incident", lambda n: sn)
    leitura = {"v": ""}
    monkeypatch.setattr(analysis.sn_api, "get_camera_code", lambda sid: leitura["v"])

    client.post("/incidents", json={"incident_number": "INC1"})
    assert client.get("/incidents/INC1").json()["titulo_padrao"] == "Barra Mansa - Câmera com imagem degradada"

    leitura["v"] = "11-SUC"  # o campo foi preenchido (ou passou a ser lido)
    r = client.post("/incidents/refresh-pendentes").json()
    assert r["relidos"] == 1 and r["mudaram"][0]["camera_codigo"] == "11-SUC"
    assert client.get("/incidents/INC1").json()["titulo_padrao"] == "Barra Mansa - Câmera 11-SUC com imagem degradada"

    leitura["v"] = ""  # leitura vazia depois não apaga o código bom
    client.post("/incidents/INC1/refresh")
    assert db.get_incident("INC1")["camera_codigo"] == "11-SUC"

    db.set_incident_status("INC1", "aprovado")
    assert client.post("/incidents/INC1/refresh").status_code == 409


def test_backfill_relê_vazio_antigo(client):
    db.save_incident("INC9", {"sys_id": "s9", "camera_codigo": ""})
    with db._conn() as conn:
        conn.execute("UPDATE incidents SET camera_lido_em=datetime('now','-2 hours') WHERE incident_number='INC9'")
    assert [r["incident_number"] for r in db.incidents_sem_camera()] == ["INC9"]
    db.set_camera("INC9", "")
    assert db.incidents_sem_camera() == []  # acabou de ler: espera 30 min


class _Resp:
    def __init__(self, status, data):
        self.status_code, self._d = status, data
        self.ok = status < 400

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _Http:
    def __init__(self, order_status=200):
        self.posts, self.order_status = [], order_status

    def get(self, url, **kw):
        if "/sys_user/" in url:
            return _Resp(200, {"result": {"user_name": "70199550", "email": "v@x", "company": {"value": "c1"},
                                          "department": {"value": "d1"}, "cost_center": {"value": "cc1"}}})
        if url.endswith("/sc_req_item"):
            return _Resp(200, {"result": [{"number": "RITM1", "sys_id": "r1"}]})
        return _Resp(200, {"result": [{"sc_item_option.value": "INC1 06-SUC"}]})

    def post(self, url, **kw):
        self.posts.append((url, kw["json"]))
        return _Resp(self.order_status, {"result": {"request_number": "REQ1", "request_id": "q1"}})


def test_submit_via_catalogo_envia_variaveis_e_le_numero():
    http = _Http()
    r = ritm.submit_via_catalog(http, "https://x", {}, "loc1", "06-SUC", "PEMT", "Causa raiz: ...")
    assert r == {"number": "RITM1", "req": "REQ1", "sys_id": "r1", "texto": "INC1 06-SUC"}
    url, body = http.posts[0]
    assert url.endswith(f"/items/{ritm.CAT_ITEM}/order_now")
    v = body["variables"]
    assert v["location_00"] == "loc1" and v["pendncia_00"] == "PEMT" and v["cost_center_cost_center"] == "cc1"
    with pytest.raises(ritm.CatalogoIndisponivel):
        ritm.submit_via_catalog(_Http(403), "https://x", {}, "loc1", "a", "PEMT", "d")


def test_ritm_de_incidente_em_andamento_fora_da_fila(client, monkeypatch):
    from backend.routes import camera, incidents
    sn = {"sys_id": "s7", "short_description": "Barra Mansa - Câmera 06-SUC sem conexão", "description": "",
          "state": "2", "assignment_group": "AMS-TI-CFTV-DBB", "u_incident_location": ""}
    monkeypatch.setattr(camera.sn_api, "get_incident", lambda n: sn)
    monkeypatch.setattr(camera.sn_api, "get_camera_code", lambda sid: "06-SUC")
    monkeypatch.setattr(incidents.sn_api, "get_current", lambda sid: {"state": "2", "work_notes": ""})
    monkeypatch.setattr(incidents.sn_api, "patch_incident", lambda sid, f: True)
    d = client.get("/incidents/INC7/ritm/draft").json()
    assert d["localidade_form"] == "CFTV - Barra Mansa" and d["subarea"] == "06-SUC"
    assert "CFTV - Barra Mansa" in d["locais"] and ritm.local_id("CFTV - Barra Mansa")
    body = {"localidade_form": d["localidade_form"], "subarea": d["subarea"], "pendencia": "Infraestrutura",
            "descricao": d["descricao"]}
    assert client.post("/incidents/INC7/ritm", json=body).status_code == 200
    assert client.post("/incidents/INC7/ritm", json=body).status_code == 409  # não duplica


def test_pedido_de_acesso():
    assert is_access_request("[CFTV] - Solicitação", "Descrição do problema: solicito acesso às câmeras da portaria")
    assert not is_access_request("Estou sem acesso às câmeras")
    inc = {"short_description": "Pedido de acesso às imagens", "description": "", "localidade": "Resende"}
    fields, warnings = build_first_touch(inc, {**inc, "grupo": "g"}, {"state": "1", "work_notes": ""})
    assert fields["short_description"] == "Resende - Solicitação de acesso às câmeras"
    assert fields["work_notes"] == WORK_NOTE_ACESSO
    msg = teams.build_message_acesso("INC1", "Ericon")
    assert "[LINK]" in msg and "LGPD" in msg and "INC1" in msg
    assert msg.split("\n")[0] in ("Bom dia, Ericon! Tudo bem?", "Boa tarde, Ericon! Tudo bem?", "Boa noite, Ericon! Tudo bem?")
    assert msg.endswith("Qualquer dúvida, fico à disposição!")
    # despacho só afirma o fato; o contato com o solicitante entra no encerramento
    assert WORK_NOTE_ACESSO.startswith("Causa raiz: Solicitação de acesso") and "Realizado contato" not in WORK_NOTE_ACESSO

"""Entrada/Saída da fila (fluxo.classificar) e pistas de localidade (IC afetado, locais). Sem rede."""
import shutil

import pytest
from fastapi.testclient import TestClient

from backend import fluxo, pistas
from backend.config import config, ROOT
from backend.rules_engine import engine

EU = "Machado, Victor Alexandre Basilio"
NOTA_MINHA = f"01/10/2026 17:48:31 - {EU} (Anotações de trabalho)\nEncaminhado para equipe.\n\n"
NOTA_OUTRO = "01/10/2026 10:00:00 - Silva, Fulano (Anotações de trabalho)\nVerificando.\n\n"


def sn(state="1", grupo=None, notas=""):
    return {"state": state, "grupo": grupo or config.QUEUE_GROUP, "work_notes": notas}


@pytest.mark.parametrize("row, atual, esperado", [
    (sn(), "analisado", "analisado"),                              # Novo na fila geral, sem nota: Entrada
    (sn(state="2"), "analisado", "tratado_fora"),                  # já em andamento
    (sn(grupo="outro-grupo"), "analisado", "tratado_fora"),        # já na fila destino
    (sn(notas=NOTA_MINHA), "analisado", "tratado_fora"),           # já tem nota minha
    (sn(notas=NOTA_OUTRO), "analisado", "analisado"),              # nota de outra pessoa não tira da Entrada
    (sn(state="8"), "analisado", "tratado_fora"),                  # 8 = Aguardando Mudança, não é encerrado
    (sn(state="7"), "aprovado", "encerrado"),
    (sn(state="24"), "analisado", "encerrado"),                    # 24 = cancelado
    (sn(state="2", grupo="outro-grupo"), "aprovado", "aprovado"),  # despachado pelo agente continua despachado
    (sn(), "encerrado", "analisado"),                              # reaberto e devolvido à fila geral
])
def test_classificar(row, atual, esperado):
    assert fluxo.classificar(row, atual, EU) == esperado


def test_autores_mais_nova_primeiro():
    assert fluxo.autores(NOTA_MINHA + NOTA_OUTRO) == [EU, "Silva, Fulano"]
    assert fluxo.autores("") == []


@pytest.fixture()
def client(tmp_path, monkeypatch):
    rules = tmp_path / "rules.json"
    shutil.copy(ROOT / "data" / "rules.json", rules)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "RULES_PATH", str(rules))
    monkeypatch.setattr(config, "SERVICENOW_DRY_RUN", True)
    from backend.main import app
    from backend.db import init_db
    engine._mtime = None
    init_db()
    return TestClient(app)


def _salvar(n, status="analisado"):
    from backend import db
    db.save_incident(n, {"sys_id": n.lower(), "short_description": "CFTV offline - PIR camera 3",
                         "localidade": "Piracicaba", "grupo": "g", "grupo_display": "AMS-TI-CFTV-PIR"}, status)


def test_reanalise_nao_devolve_para_entrada(client):
    from backend import db
    _salvar("INC1")
    db.set_incident_status("INC1", "aprovado")
    _salvar("INC1")  # Processar/Reler de novo
    inc = db.get_incident("INC1")
    assert inc["status"] == "aprovado" and inc["saiu_em"]
    assert [i["incident_number"] for i in db.list_saida()] == ["INC1"]
    assert db.list_incidents(only_pending=True) == []


def test_lista_entrada_nao_chama_servicenow(client, monkeypatch):
    from backend.routes import incidents

    def proibido(*a, **k):
        raise AssertionError("GET /incidents não deve consultar o ServiceNow")
    monkeypatch.setattr(incidents.sn_api, "get_incident", proibido)
    _salvar("INC2")
    assert [i["incident_number"] for i in client.get("/incidents").json()] == ["INC2"]
    assert client.get("/incidents/saida").json() == []


def test_reconciliar_move_para_saida(client, monkeypatch):
    from backend import db
    _salvar("INC3")
    _salvar("INC4")
    monkeypatch.setattr(config, "SERVICENOW_MOCK", False)
    monkeypatch.setattr(fluxo.sn_api, "meu_nome", lambda: EU)
    monkeypatch.setattr(fluxo.sn_api, "estado_lote", lambda ids: [
        {"sys_id": "inc3", "number": "INC3", "state": "1", "grupo": config.QUEUE_GROUP, "grupo_nome": "AMS-TI-CFTV",
         "work_notes": NOTA_MINHA},
        {"sys_id": "inc4", "number": "INC4", "state": "1", "grupo": config.QUEUE_GROUP, "grupo_nome": "AMS-TI-CFTV",
         "work_notes": ""}])
    r = fluxo.reconciliar()
    assert r["mudaram"] == [("INC3", "analisado", "tratado_fora")]
    assert db.get_incident("INC3")["nota_autor"] == EU
    assert [i["incident_number"] for i in db.list_incidents(only_pending=True)] == ["INC4"]


def test_encerrar_so_da_saida_e_respeita_dry_run(client, monkeypatch):
    from backend import db
    from backend.routes import incidents
    enviados = []
    monkeypatch.setattr(incidents.sn_api, "patch_incident", lambda sid, f: enviados.append(f) or True)
    _salvar("INC5")
    r = client.post("/incidents/INC5/close", json={"work_notes": "Causa base: teste."})
    assert r.status_code == 409 and "Entrada" in r.json()["detail"]
    db.set_incident_status("INC5", "aprovado")
    assert client.post("/incidents/INC5/close", json={"work_notes": " "}).status_code == 422
    r = client.post("/incidents/INC5/close", json={"work_notes": "Causa base: teste."}).json()
    assert r["simulado"] is True
    assert r["fields"]["state"] == "6" and r["fields"]["close_code"] == "Solved" and "comments" not in r["fields"]
    assert db.get_incident("INC5")["status"] == "aprovado"  # simulado não muda o status local


# ---- pistas ----

def test_ic_de_servidor_define_a_unidade_do_alerta():
    inc = {"short_description": "Percentage of used network adapter total bandwidth is over threshold.",
           "caller_id": "LCB, MONITORING", "cmdb_ci": "LCB - PRJ-APP-CFTV02",
           "cmdb_ci_location": "Longos - USINA PIRACICABA"}
    p = pistas.coletar(inc)
    assert p[0] == {"fonte": "IC afetado", "valor": "PRJ-APP-CFTV02", "unidade": "Projects (monitoramento)",
                    "peso": pistas.PESO_HOST}
    r = engine.apply_rules(inc)
    assert r["grupo_display"] == "AMS-TI-CFTV-PRJ" and r["localidade_confianca"] == 100
    assert "IC afetado PRJ-APP-CFTV02" in r["motivo"] and not r.get("conflito")


def test_alerta_de_banda_em_servidor_de_unidade():
    r = engine.apply_rules({"short_description": "Percentage of used network adapter total bandwidth is over threshold.",
                            "caller_id": "LCB, MONITORING", "cmdb_ci": "LCB - SAB-APP-CFTV01"})
    assert r["localidade"] == "Sabará"


def test_local_do_ic_quando_o_texto_nao_diz():
    assert pistas.unidade_do_local("Longos - USINA PIRACICABA") == "Piracicaba"
    assert pistas.unidade_do_local("Escritório BH") is None
    r = engine.apply_rules({"short_description": "[CFTV] - Imagem degradada", "cmdb_ci_location": "Longos - USINA SABARA"})
    assert r["localidade"] == "Sabará" and r["localidade_confianca"] == pistas.PESO_LOCAL
    assert "pista: local do IC" in r["motivo"]


def test_ic_em_conflito_com_o_texto_baixa_a_confianca():
    r = engine.apply_rules({"short_description": "CFTV offline - PIR camera 3", "cmdb_ci": "LCB - SRV-CFTV-GUA"})
    assert r["localidade"] == "Piracicaba"
    assert r["localidade_confianca"] < config.CONFIDENCE_THRESHOLD and r["conflito"]
    assert "conflito: IC afetado SRV-CFTV-GUA" in r["motivo"]


def test_sem_ic_continua_nas_regras():
    r = engine.apply_rules({"short_description": "CFTV offline - PIR camera 3"})
    assert r["localidade"] == "Piracicaba" and r["pistas"] == [] and r["localidade_confianca"] == 100

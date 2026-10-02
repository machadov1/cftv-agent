from backend import scom
from backend.servicenow_mock import MOCK_INCIDENTS


def test_extrai_host_do_alerta():
    i = MOCK_INCIDENTS["INC9000008"]
    assert scom.is_scom_alert(i["short_description"], i["description"])
    assert scom.extract_host(i["short_description"], i["description"]) == "BBD-APP-CFTV02"
    real = "The Health Service on computer PIR-APP-CFTV03.Americas.mittalco.com failed to heartbeat."
    assert scom.extract_host("x", real) == "PIR-APP-CFTV03"


def test_ping_localhost_e_host_invalido():
    r = scom.run_ping("localhost", domain="")
    assert r["ok"] and r["perda_percentual"] == 0
    import pytest
    with pytest.raises(ValueError):
        scom.run_ping("a; calc")


def test_sem_resolucao_nao_gera_work_note():
    r = scom.check("Alerta", "on computer HOST-NAO-EXISTE-XYZ.Americas.mittalco.com failed to heartbeat", evidence=False)
    assert not r["ok"] and r["work_note"] is None


def test_alerta_vai_para_a_unidade_do_host(monkeypatch):
    from backend.rules_engine import engine
    from backend.payload import build_first_touch, display_title
    from backend import servidores
    monkeypatch.setattr(servidores, "find", lambda h: None)  # só o prefixo do nome, sem depender da planilha
    titulo = ("Servidor nao esta comunicando com SCOM server, verificar ou restartar o servico System Center Managament ou "
              "Microsoft Monitoring Agent - The System Center Management Health Service on computer {h}.Americas.mittalco.com "
              "failed to heartbeat.")
    for host, loc, grupo in (("RES-APP-CFTV04", "Resende", "AMS-TI-CFTV-DBC"),
                             ("IRA-APP-CFTV02", "Iracemápolis", "AMS-TI-CFTV-BZX")):
        r = engine.apply_rules({"short_description": titulo.format(h=host), "description": ""})
        assert (r["localidade"], r["grupo_display"], r["localidade_confianca"]) == (loc, grupo, 100)
        inc = {"short_description": titulo.format(h=host), "description": "", "localidade": loc}
        assert display_title(inc)["titulo_padrao"] == inc["short_description"]  # título do alerta preservado
        fields, _ = build_first_touch(inc, {**inc, "grupo": r["grupo"]}, {"state": "1", "work_notes": ""})
        assert "short_description" not in fields and "category" not in fields and fields["assignment_group"] == r["grupo"]
    # host sem unidade conhecida: continua em Projects
    r = engine.apply_rules({"short_description": titulo.format(h="XYZ-APP-01"), "description": ""})
    assert r["localidade"] == "Projects (monitoramento)"

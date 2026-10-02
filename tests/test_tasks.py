"""Painel de TASKs de acesso a imagens: leitura do texto da tarefa (dois formulários) e resumo. Sem rede."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend import tasks
from backend.config import config

NOW = datetime(2026, 10, 1, 14, 0, tzinfo=timezone(timedelta(hours=-3)))
CFTV = ("\n\n Informações da Requisição\nSolicitante : Benedito, Renan Mendes\nDepartamento : 50027844\n"
        "E-mail : renan.benedito@arcelormittal.com.br\nGerência : SUP PROD LAMINAC 03 A\nÁrea das Câmeras : GAPLA 3\n"
        "Localidade : CFTV - Monlevade\nDescrição detalhada : Liberação do acesso as câmeras do CFTV, do LAMINADOR 3.\n"
        "Tipo: : Visualização\n")
DIGIFORT = ("\n\n Informações da Requisição\nAberto por : Rocha, Francisco Sergio\nSolicitado para : Rocha, Francisco Sergio\n"
            "Empresa : ArcelorMittal Pecem\nDepartamento : SUP INFRA ESTRUT TI TA\nCost center: : SP00-TI261\n"
            "Justificativa : Acesso as cameras das salas de servidores\nVisualização : Verdadeiro(a)\n"
            "Reprodução : Falso(a)\nExportação : Verdadeiro(a)\nÁrea : T.I\nLocalização (Prédio) : ADM 6\nSala : T.I.\n")


def raw(desc, user="", resp="", dias=2):
    op = (NOW - timedelta(days=dias)).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return {"number": "TASK1", "sys_id": {"value": "s1"}, "description": desc, "request_item": {"display_value": "RITM1"},
            "assigned_to": {"display_value": resp}, "assigned_to.user_name": {"value": user}, "opened_at": {"value": op},
            "state": {"display_value": "Aberto"}}


def test_formulario_cftv():
    t = tasks.normalize(raw(CFTV), NOW, "70199550")
    assert (t["solicitante"], t["area"], t["unidade"], t["tipo"]) == ("Benedito, Renan Mendes", "GAPLA 3", "João Monlevade", "Visualização")
    assert t["justificativa"].startswith("Liberação") and t["idade_dias"] == 2 and not t["meu"] and t["responsavel"] is None
    assert t["link"].endswith("/sc_task.do?sys_id=s1")


def test_formulario_digifort_pecem():
    t = tasks.normalize(raw(DIGIFORT, "70199550", "Machado, Victor"), NOW, "70199550")
    assert t["solicitante"] == "Rocha, Francisco Sergio" and t["unidade"] == "Pecém"
    assert t["tipo"] == "Visualização + Exportação" and t["area"] == "T.I · ADM 6 · T.I." and t["meu"]


def test_unidade_por_texto_da_localidade():
    assert tasks.unidade("CFTV - Mina Serra Azul") == "Serra Azul"
    assert tasks.unidade("CFTV - Entreposto Igarapé") == "Igarapé"
    assert tasks.unidade("CFTV - BBA  - CTG") == "BBA - CTG"
    assert tasks.unidade(None) is None


def test_rota_em_mock(monkeypatch):
    monkeypatch.setattr(config, "SERVICENOW_MOCK", True)
    tasks._cache.update(at=0.0, data=None)
    from backend.main import app
    d = TestClient(app).get("/tasks?force=true").json()
    assert d["kpis"]["total"] == 3 and d["kpis"]["meus"] == 1 and d["kpis"]["sem_responsavel"] == 1
    assert d["kpis"]["mais_de_7_dias"] == 1 and d["rows"][0]["number"] == "TASK9000003"  # mais antiga primeiro
    tasks._cache.update(at=0.0, data=None)


def test_formulario_antigo_descricao_em_varias_linhas():
    desc = ("\n\n Informações da Requisição\nSolicitante : Oliveira, Marcony\nÁrea das Câmeras : Logística / Ambiental\n"
            "Localidade : CFTV - Barra Mansa\nDescrição : Exportar as imagens:\nBM-LOG-C-016 dia 07/08/2026 das 19:00 às 20:00\n"
            "BM-AMB-A-001 dia 13/08/2026 das 19:00\nTipo: : Exportação\n")
    t = tasks.normalize(raw(desc), NOW, None)
    assert t["justificativa"] == ("Exportar as imagens: BM-LOG-C-016 dia 07/08/2026 das 19:00 às 20:00 "
                                  "BM-AMB-A-001 dia 13/08/2026 das 19:00")
    assert (t["tipo"], t["unidade"]) == ("Exportação", "Barra Mansa")

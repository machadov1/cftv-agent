"""Topologia unidade -> servidores -> câmeras: lista do CSV (sem colunas sensíveis) e leitura sob demanda do Digifort."""
import pytest
from fastapi.testclient import TestClient

from backend import digifort, servidores
from backend.config import config

CSV = (
    "Unidade ,Nome Do Ativo ,IP ,Tipo de Ativo ,Senha ,Senha Digifort \n"
    "Pecém ,PEC-APP-CFTV01,10.1.0.1,Servidor CFTV,segredo1,segredo2\n"
    "Pecém,PEC-APP-CFTV02,10.1.0.2,Faillover CFTV,segredo1,segredo2\n"
    "Barra Mansa,BMA-APP-CFTV01,10.2.0.1,Servidor CFTV,segredo1,segredo2\n"
    "Barra Mansa,BMA-STG01,10.2.0.9,Storage,segredo1,segredo2\n"
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    arq = tmp_path / "servidores.csv"
    arq.write_text(CSV, encoding="utf-8")
    monkeypatch.setattr(servidores, "PATH", arq)
    servidores._cache.update(mtime=None, rows=[])
    monkeypatch.setattr(config, "DIGIFORT_USER", "svc")
    monkeypatch.setattr(config, "DIGIFORT_PASSWORD", "x")
    digifort._inv.clear()
    from backend.main import app
    return TestClient(app)


def test_topologia_agrupa_unidade_limpa_e_sem_senhas(client):
    r = client.get("/servidores/topologia")
    unidades = r.json()["unidades"]
    assert [u["unidade"] for u in unidades] == ["Barra Mansa", "Pecém"]
    pec = unidades[1]["servidores"]
    assert [s["nome"] for s in pec] == ["PEC-APP-CFTV01", "PEC-APP-CFTV02"]  # principal antes do failover
    assert "segredo" not in r.text and "BMA-STG01" not in r.text  # sem senhas e só CFTV


def test_servidor_le_cameras_e_resume(client, monkeypatch):
    cams = [{"nome": "A", "descricao": "", "grupo": "", "active": True, "working": True, "inactive_s": 0},
            {"nome": "B", "descricao": "", "grupo": "", "active": True, "working": False, "inactive_s": 300},
            {"nome": "C", "descricao": "", "grupo": "", "active": False, "working": False, "inactive_s": 0}]
    monkeypatch.setattr(digifort, "inventario", lambda ip, forcar=False: {"ip": ip, "lido_em": "02/10 10:00", "cameras": cams})
    r = client.get("/servidores/topologia/10.2.0.1").json()
    assert r["ok"] and r["resumo"] == {"total": 3, "ok": 1, "sem_sinal": 1, "desativadas": 1}


def test_servidor_com_erro_volta_tipo(client, monkeypatch):
    def falha(ip, forcar=False):
        raise digifort.DigifortError(f"{ip}: usuário/senha recusados", "credencial")
    monkeypatch.setattr(digifort, "inventario", falha)
    r = client.get("/servidores/topologia/10.1.0.1").json()
    assert not r["ok"] and r["tipo_erro"] == "credencial" and r["cameras"] == []


def test_ip_fora_da_lista_nao_e_consultado(client, monkeypatch):
    monkeypatch.setattr(digifort, "inventario", lambda ip, forcar=False: pytest.fail("não deveria consultar"))
    assert client.get("/servidores/topologia/8.8.8.8").status_code == 404
    assert client.get("/servidores/topologia/10.2.0.9").status_code == 404  # storage não é Digifort


def test_serie_diaria_preenche_dias_sem_movimento(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "s.db"))
    from backend import db
    db.init_db()
    db.add_history("INC1", "aprovado", "x", False, 0)
    db.add_history("INC1", "analise", "x", False, 0)
    s = db.serie_diaria(5)
    assert len(s) == 5 and s[-1]["despachos"] == 1 and s[-1]["analises"] == 1 and s[0]["despachos"] == 0

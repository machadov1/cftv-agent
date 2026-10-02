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


def test_resumir_disponibilidade_sem_contar_reserva_e_desativadas():
    from backend import topologia as topo

    def c(nome, active=True, working=True):
        return {"nome": nome, "active": active, "working": working}
    unidades = [{"unidade": "Barra Mansa", "servidores": [
        {"nome": "PRINCIPAL", "ip": "1", "tipo": "Servidor CFTV"},
        {"nome": "RESERVA", "ip": "2", "tipo": "Faillover CFTV"},
        {"nome": "FORA", "ip": "3", "tipo": "Servidor CFTV"},
        {"nome": "SEM-IP", "ip": None, "tipo": "Servidor CFTV"}]}]
    leituras = {"1": {"cameras": [c("A"), c("B"), c("C", working=False), c("D", active=False)], "lido_em": "x"},
                "2": {"cameras": [c("A", active=False), c("B", active=False)], "lido_em": "x"},
                "3": {"erro": "recusada", "tipo_erro": "credencial"}}
    u = topo.resumir(unidades, leituras)[0]
    principal, reserva, fora, sem_ip = u["servidores"]
    assert principal["cameras"]["disponibilidade"] == pytest.approx(66.7) and not principal["reserva"]
    assert reserva["reserva"] and reserva["cameras"]["disponibilidade"] is None
    assert fora["ok"] is False and fora["tipo_erro"] == "credencial" and sem_ip["ok"] is None
    # A e B aparecem nos dois servidores: contam uma vez, com o estado da cópia ativa
    assert u["cameras"]["ativas"] == 3 and u["cameras"]["ok"] == 2
    assert (u["servidores_respondendo"], u["servidores_total"]) == (2, 3)


def test_rota_mapa(client, monkeypatch):
    cams = [{"nome": "A", "descricao": "", "grupo": "", "active": True, "working": True, "inactive_s": 0}]
    monkeypatch.setattr(digifort, "inventario", lambda ip, forcar=False: {"ip": ip, "lido_em": "x", "cameras": cams})
    r = client.get("/servidores/topologia/mapa").json()
    assert r["geral"]["disponibilidade"] == 100.0 and r["geral"]["servidores_respondendo"] == 3 and r["lido_em"]


def test_mapa_abre_na_leitura_salva_e_so_rele_quando_pede(client, monkeypatch):
    lidos = []

    def inv(ip, forcar=False):
        lidos.append(ip)
        return {"ip": ip, "lido_em": "x", "cameras": [{"nome": "A", "active": True, "working": True}]}
    monkeypatch.setattr(digifort, "inventario", inv)
    primeira = client.get("/servidores/topologia/mapa").json()
    assert len(lidos) == 3
    segunda = client.get("/servidores/topologia/mapa").json()
    assert len(lidos) == 3 and segunda["lido_em"] == primeira["lido_em"]  # sem nova leitura ao reabrir
    client.get("/servidores/topologia/mapa?forcar=true")
    assert len(lidos) == 6


def test_servidor_escondido_some_do_mapa_e_nao_e_lido(client, monkeypatch):
    lidos = []

    def inv(ip, forcar=False):
        lidos.append(ip)
        return {"ip": ip, "lido_em": "x", "cameras": []}
    monkeypatch.setattr(digifort, "inventario", inv)
    assert client.put("/servidores/10.2.0.1/desabilitado", json={"disabled": True}).json()["disabled"] is True
    r = client.get("/servidores/topologia/mapa?forcar=true").json()
    assert "10.2.0.1" not in lidos and [u["unidade"] for u in r["unidades"]] == ["Pecém"]  # Barra Mansa ficou vazia
    cfg = {s["ip"]: s for s in client.get("/servidores/config").json()["servidores"]}
    assert cfg["10.2.0.1"]["disabled"] and not cfg["10.1.0.1"]["disabled"]
    client.put("/servidores/10.2.0.1/desabilitado", json={"disabled": False})
    assert len(client.get("/servidores/topologia/mapa").json()["unidades"]) == 2  # volta sem precisar reler tudo


def test_senha_propria_grava_rele_e_nao_volta_na_lista(client, monkeypatch):
    def inv(ip, forcar=False):
        if digifort._cred(ip)[1] != "certa":
            raise digifort.DigifortError(f"{ip}: usuário/senha recusados", "credencial")
        return {"ip": ip, "lido_em": "x", "cameras": [{"nome": "A", "active": True, "working": True}]}
    monkeypatch.setattr(digifort, "inventario", inv)
    client.get("/servidores/topologia/mapa")
    assert client.post("/servidores/credencial/10.1.0.1", json={"usuario": "adm", "senha": "errada"}).json()["tipo_erro"] == "credencial"
    r = client.post("/servidores/credencial/10.1.0.1", json={"usuario": "adm", "senha": "certa"}).json()
    assert r["ok"] is True and r["cameras"] == 1
    lista = client.get("/servidores/config")
    srv = {s["ip"]: s for s in lista.json()["servidores"]}["10.1.0.1"]
    assert srv["usuario_proprio"] == "adm" and srv["ok"] is True and "certa" not in lista.text
    mapa = client.get("/servidores/topologia/mapa").json()  # a leitura salva já tem o servidor corrigido
    pec = next(u for u in mapa["unidades"] if u["unidade"] == "Pecém")
    assert pec["servidores"][0]["ok"] is True
    assert client.delete("/servidores/credencial/10.1.0.1").json()["ok"] is False  # volta à padrão (recusada)

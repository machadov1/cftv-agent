from backend import scom, servidores

CSV = (
    '"Unidade","Cliente","Nome Do Ativo","IP","Usuário ","Senha ","Tipo de Ativo","IP da iLO","Senha da iLO","Observações Gerais"\n'
    '"Bauru","ArcelorMittal","BBD-APP-CFTV01","10.58.36.20","admin","segredo123","Servidor CFTV","10.58.36.18","ilo-secreta",\n'
    '"Barra Mansa",,"Ceva","10.58.68.25","administrador","outra","Servidor Analítico",,,"-"\n'
)


def _usar(tmp_path, monkeypatch):
    f = tmp_path / "servidores.csv"
    f.write_text(CSV, encoding="utf-8")
    monkeypatch.setattr(servidores, "PATH", f)
    servidores._cache.update(mtime=None, rows=[])


def test_lista_so_colunas_seguras(tmp_path, monkeypatch):
    _usar(tmp_path, monkeypatch)
    assert servidores.status() == {"carregado": True, "total": 2}
    blob = str(servidores.find("bbd-app-cftv01"))
    assert "segredo123" not in blob and "ilo-secreta" not in blob and "admin" not in blob
    assert servidores.find("BBD-APP-CFTV01")["ip"] == "10.58.36.20"
    assert servidores.find("10.58.36.18")["nome"] == "BBD-APP-CFTV01"  # por IP da iLO


def test_detecta_no_texto_e_trata_traco_como_vazio(tmp_path, monkeypatch):
    _usar(tmp_path, monkeypatch)
    assert servidores.detect("Servidor Ceva fora do ar")["unidade"] == "Barra Mansa"
    assert servidores.find("Ceva")["obs"] is None
    assert servidores.detect("Queda em XYZ-APP-CFTV09")["nome"] == "XYZ-APP-CFTV09"
    assert servidores.detect("sem nada de servidor aqui") is None


def test_sem_arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(servidores, "PATH", tmp_path / "nao-existe.csv")
    servidores._cache.update(mtime=None, rows=[])
    assert servidores.status() == {"carregado": False, "total": 0}
    assert servidores.find("x") is None


def test_ping_host_geral_nao_gera_texto_de_encerramento():
    r = scom.ping_host("localhost", evidence=False)
    assert r["work_note"] is None and r["host"] == "localhost"

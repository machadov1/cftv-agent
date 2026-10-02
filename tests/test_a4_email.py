"""E-mail A4: modelo do .oft preenchido, prévia sem abrir nada, nunca envia. Sem rede, sem Outlook."""
import shutil
from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from backend import a4
from backend.config import config, ROOT


def test_email_preenche_o_modelo():
    m = a4.email_a4("INC4005519", "Guarulhos", "Dispositivo WUB da empilhadeira 12 sem comunicação",
                    "Costa, Ericon", "ericon@x.com", "05/10/2026 18:00", hora=9)
    assert m["assunto"] == "Incidente A4 - INC4005519 - ArcelorMittal (Guarulhos)"  # sem "INCINC"
    assert m["corpo"].startswith("Bom dia!\n") and "Bom Bom" not in m["corpo"]
    for trecho in ("WUB da empilhadeira 12", "Usuário: Costa, Ericon", "E-mail: ericon@x.com",
                   "Unidade/Segmento: Guarulhos", "SLA: 05/10/2026 18:00", "Victor Basílio Machado"):
        assert trecho in m["corpo"]
    assert m["para"] == "servicedesk@alertsystem.com.br" and m["cc"] == "felipe.borges@alertsystem.com.br"
    assert m["mailto"].startswith("mailto:servicedesk@alertsystem.com.br?cc=felipe.borges@alertsystem.com.br&subject=")
    assert "Bom dia!\r\n" in unquote(m["mailto"])


@pytest.mark.parametrize("hora, saud", [(8, "Bom dia"), (13, "Boa tarde"), (19, "Boa noite")])
def test_saudacao_pela_hora(hora, saud):
    assert a4.email_a4("INC1", "Resende", "x", hora=hora)["corpo"].startswith(f"{saud}!")


def test_agente_nunca_envia_email():
    fontes = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "backend").rglob("*.py"))
    assert ".Send(" not in fontes and "win32com" not in fontes


@pytest.fixture()
def client(tmp_path, monkeypatch):
    rules = tmp_path / "rules.json"
    shutil.copy(ROOT / "data" / "rules.json", rules)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "RULES_PATH", str(rules))
    from backend.main import app
    from backend.db import init_db, save_incident
    from backend.routes import incidents
    from backend.rules_engine import engine
    engine._mtime = None
    init_db()
    save_incident("INC9", {"sys_id": "s9", "short_description": "EQUIPE GUA A4 - Dispositivo WUB de Smart Safety da empilhadeira",
                           "description": "Dispositivo WUB de Smart Safety da empilhadeira 7 sem sinal.",
                           "localidade": "Guarulhos", "caller_id": "Costa, Ericon"}, "aprovado")
    monkeypatch.setattr(incidents.sn_api, "get_incident",
                        lambda n: {"sys_id": "s9", "number": n, "due_date": "2026-10-05 21:00:00"})
    monkeypatch.setattr(incidents.sn_api, "get_caller", lambda sid: {"nome": "Costa, Ericon", "email": "e@x.com"})
    return TestClient(app)


def test_previa_e_abertura_registram_sem_enviar(client):
    prev = client.get("/incidents/INC9/email-a4/preview").json()
    assert "SLA: 05/10/2026 18:00" in prev["corpo"]  # UTC -> Brasília
    assert "empilhadeira 7" in prev["corpo"]
    r = client.post("/incidents/INC9/email-a4").json()
    assert r["sucesso"] and r["mailto"] == prev["mailto"] and r["ja_aberto_antes"] == 0
    assert client.post("/incidents/INC9/email-a4").json()["ja_aberto_antes"] == 1


def test_previa_recusa_incidente_que_nao_e_a4(client):
    from backend.db import save_incident
    save_incident("INC8", {"sys_id": "s8", "short_description": "CFTV offline - PIR camera 3"}, "aprovado")
    assert client.get("/incidents/INC8/email-a4/preview").status_code == 409

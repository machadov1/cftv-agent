import pytest


@pytest.fixture(autouse=True)
def _sem_llm_real(monkeypatch):
    """Testes nunca chamam provedores reais (o 9router local estaria disponível na máquina)."""
    from backend import llm

    def boom(*a, **k):
        raise llm.LLMError("LLM desligado nos testes")
    monkeypatch.setattr(llm, "available", lambda: False)
    for nome in ("chat", "call", "test_provider", "list_models"):
        monkeypatch.setattr(llm, nome, boom)


@pytest.fixture(autouse=True)
def _sem_rede_externa(monkeypatch):
    """Nem ServiceNow (formulário da câmera) nem Digifort são chamados de verdade nos testes."""
    from backend import digifort
    from backend.servicenow_api import ServiceNowAPI

    monkeypatch.setattr(ServiceNowAPI, "get_camera_code", lambda self, sys_id: None)
    monkeypatch.setattr(ServiceNowAPI, "estado_lote", lambda self, sys_ids: [])
    monkeypatch.setattr(ServiceNowAPI, "meu_nome", lambda self: None)

    def sem_rede(*a, **k):
        raise AssertionError("teste tentou chamar o Digifort de verdade")
    monkeypatch.setattr(digifort.requests, "get", sem_rede)

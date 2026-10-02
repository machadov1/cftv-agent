"""Regras do manual de textos de encerramento (backend/textos.py) e o redator com IA (sem LLM real)."""
import pytest

from backend import llm, redator, textos


def test_blocos_na_ordem_e_analise_em_lista():
    t = textos.montar("Câmera PIR400 sem conexão", ["PIR400: cabo rompido", "PIR401: aguardando PEMT"],
                      "Realizada troca do cabo", "Aguardando disponibilização da PEMT",
                      textos.COM_PENDENCIA, "Leila Da Conceicao Canazart")
    assert t == ("Causa raiz: Câmera PIR400 sem conexão.\n\n"
                 "Análise:\n\n- PIR400: cabo rompido.\n- PIR401: aguardando PEMT.\n\n"
                 "Resolução: Realizada troca do cabo.\n\n"
                 "Encaminhamento: Aguardando disponibilização da PEMT.\n\n"
                 "Encerramento: Incidente encerrado com pendência vinculada à requisição. "
                 "Validação: Canazart, Leila Da Conceicao.")


def test_validacao_sobrenome_nome():
    assert textos.validacao_fmt("Leila Canazart") == "Canazart, Leila"
    assert textos.validacao_fmt("Canazart, Leila") == "Canazart, Leila"
    assert textos.validacao_fmt("  ") is None
    t = textos.com_validacao("Causa raiz: x.\n\nEncerramento: Incidente encerrado.", "Ana Souza")
    assert t.endswith("Encerramento: Incidente encerrado. Validação: Souza, Ana.")
    assert textos.com_validacao(t, "Outro Nome") == t  # não duplica


def test_revisar_corrige_sem_comentar_e_protege_dados():
    t, avisos = textos.revisar("Causa base: Câmera restabelecida. Restabelecimento ok. senha: Abc@123 CPF 123.456.789-09 "
                               "https://amamericas.service-now.com/x?sys_id=1&RITM1234567\n\nEncerramento: Incidente encerrado.")
    assert t.startswith("Causa raiz: Câmera reestabelecida. Reestabelecimento ok.")
    assert "Abc@123" not in t and "senha: [credencial]" in t and "[CPF]" in t and "RITM1234567" in t
    assert "service-now" not in t
    assert any("Credencial" in a for a in avisos) and not textos.bloqueios(t)  # [credencial]/[CPF] não bloqueiam


def test_bloqueios_de_modelo_nao_preenchido():
    assert textos.bloqueios("Encaminhamento: vinculado à requisição [RITM].") == ["[RITM]"]
    assert textos.bloqueios(textos.simples(None)) == ["[sintoma e ativo afetado]", "[descreva a ação executada]"]
    assert textos.bloqueios("Causa raiz: Câmera RES027 sem conexão.") == []
    _, avisos = textos.revisar("Causa raiz: x.")
    assert any("Incidente encerrado" in a for a in avisos)


def test_camera_verificada_nao_diz_reestabelecida_e_pendencia_pede_ritm():
    t = textos.camera_verificada("Câmeras 399, 407  sem conexão", ["399", "407"])
    assert "reestabelec" not in t.lower() and "de que as câmeras se encontram operando normalmente" in t
    assert t.startswith("Causa raiz: Câmeras 399, 407 sem conexão.")  # espaço duplo do título some
    assert t.endswith("Encerramento: Incidente encerrado.")
    p = textos.camera_verificada(None, ["399"], ["393"])
    assert p.startswith("Causa raiz: Câmeras 399, 393 sem conexão.")
    assert "- 393: sem sinal no Digifort no momento da checagem." in p and textos.bloqueios(p) == ["[RITM]"]
    assert p.endswith(textos.COM_PENDENCIA)


def test_ritm_numero_so_no_encaminhamento_e_sla():
    d = textos.ritm_descricao("Câmera RES027 sem conexão", "Andaime", sla_proximo=True)
    assert "Reparo depende de montagem de andaime para acesso ao ponto. Considerando a proximidade" in d
    assert "Aguardando montagem do andaime. Acompanhamento seguirá vinculado à requisição." in d
    n = textos.com_ritm(d, "RITM1234567")
    assert "vinculado à requisição RITM1234567." in n and n.endswith("pendência vinculada à requisição.")


def test_causa_do_titulo():
    assert textos.causa_do_titulo("Piracicaba - Câmeras 399, 407 sem conexão", "Piracicaba") == "Câmeras 399, 407 sem conexão"
    assert textos.causa_do_titulo("[BR-SD] CFTV LONGOS - PROBLEMAS EM GERAL", "Piracicaba") is None


# ---------- redator (IA) ----------
@pytest.fixture()
def resposta(monkeypatch):
    enviado = {}

    def fake(conteudo):
        def chat(messages, **k):
            enviado["messages"] = messages
            return {"message": {"content": conteudo}, "model": "fake"}
        monkeypatch.setattr(llm, "chat", chat)
        return enviado
    return fake


def test_redator_usa_o_manual_e_revisa_a_saida(resposta):
    enviado = resposta("```\n**Causa base:** Câmera PIR400 sem conexão.\n\nResolução: Troca do patch cord. Câmera "
                       "restabelecida, operando normalmente.\n\nEncerramento: Incidente encerrado.\nAVISO: confira o código\n```")
    r = redator.redigir({"incident_number": "INC1", "cameras": "PIR400", "modelo": "Causa raiz: ..."},
                        "trocado patch cord", "enxuto")
    sistema, usuario = enviado["messages"][0]["content"], enviado["messages"][1]["content"]
    assert "Regra de ouro" in sistema and "Comandos rápidos" in sistema  # manual inteiro na instrução
    assert "trocado patch cord" in usuario and "Comando 'enxuto'" in usuario and "PIR400" in usuario
    assert r["texto"].startswith("Causa raiz: Câmera PIR400") and "reestabelecida" in r["texto"]
    assert "**" not in r["texto"] and "```" not in r["texto"] and "AVISO" not in r["texto"]
    assert "confira o código" in r["avisos"]


def test_redator_devolve_pergunta(resposta):
    resposta("PERGUNTA: Qual foi o resultado da tratativa?")
    assert redator.redigir({"incident_number": "INC1"}, "câmera sem imagem") == {
        "pergunta": "Qual foi o resultado da tratativa?", "modelo": "fake"}


def test_redator_comando_desconhecido():
    with pytest.raises(ValueError):
        redator.redigir({}, "x", "inventa")

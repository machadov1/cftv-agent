import pytest
from backend.rules_engine import RulesEngine
from backend.servicenow_mock import MOCK_INCIDENTS

# incidente -> (localidade, grupo_display, ritm)
ESPERADO = {
    "INC9000001": ("Piracicaba", "AMS-TI-CFTV-PIR", False),
    "INC9000002": ("Barra Mansa", "AMS-TI-CFTV-DBB", False),
    "INC9000003": ("Resende", "AMS-TI-CFTV-DBC", False),
    "INC9000004": ("Piracicaba (LORA)", "AMS-TI-LORA-PIR", False),
    "INC9000005": ("João Monlevade", "AMS-TI-CFTV-MDE", False),
    "INC9000006": (None, None, False),
    "INC9000007": ("Serra Azul", None, False),      # nunca mover sozinho
    "INC9000008": ("Bauru", "AMS-TI-CFTV-BBD", False),  # alerta vai para a unidade do host
    "INC9000009": ("Juiz de Fora", "AMS-TI-CFTV-JUA", True),
}


@pytest.mark.parametrize("numero", sorted(ESPERADO))
def test_cenario(numero):
    r = RulesEngine().apply_rules(MOCK_INCIDENTS[numero])
    loc, grupo, ritm = ESPERADO[numero]
    assert (r["localidade"], r["grupo_display"] if grupo else None, r["ritm_necessaria"]) == (loc, grupo, ritm)


def test_payload_primeira_tratativa():
    from backend.payload import build_first_touch
    inc = MOCK_INCIDENTS["INC9000001"]
    final = {"localidade": "Piracicaba", "grupo": "287a11d0dbd9b7c0e5f36451ca961955"}
    f, w = build_first_touch(inc, final, {"state": "1", "work_notes": ""})
    assert f["short_description"] == "Piracicaba - Câmera PIR064 sem conexão"
    assert f["state"] == "2" and f["category"] == "network" and f["cmdb_ci"] and f["work_notes"] == "Encaminhado para equipe."
    assert w == []


def test_payload_nao_duplica_nota_e_lora_e_alerta():
    from backend.payload import build_first_touch
    f, w = build_first_touch(MOCK_INCIDENTS["INC9000001"], {"localidade": "Piracicaba", "grupo": "g"},
                             {"state": "1", "work_notes": "Encaminhado para equipe."})
    assert "work_notes" not in f and w
    f, _ = build_first_touch(MOCK_INCIDENTS["INC9000004"], {"localidade": "Piracicaba (LORA)", "grupo": "g"}, None)
    assert f["category"] == "hardware" and f["u_incident_type"] == "7bec9dfedb913700e5f36451ca9619c6"
    assert f["short_description"] == "Piracicaba - TAG LORA 808 - Falha de funcionalidade"
    f, _ = build_first_touch(MOCK_INCIDENTS["INC9000008"], {"localidade": "Projects (monitoramento)", "grupo": "g"}, None)
    assert "short_description" not in f and "category" not in f


# Incidentes reais da fila AMS-TI-CFTV (texto original do ServiceNow) -> título no padrão da skill (seção 10)
REAIS = [
    ("Jaboatão", "[CFTV] - Servidor sem conexão", "servidores de AM - Jaboatão fora de acesso",
     "Jaboatão - Servidor sem conexão"),
    ("Resende", "[CFTV] - Câmeras sem conexão", "Link de acesso as câmeras de Resende apresentam instabilidade na conexão.",
     "Resende - Câmeras sem conexão"),
    ("Piracicaba", "[Outros Sistemas] -  - Falha de Funcionalidade",
     "Câmeras da unidade de AM- Piracicaba sem conexão. Tanto para a equipe do CFTV quanto para o pátio.",
     "Piracicaba - Câmeras sem conexão"),
    ("Piracicaba", "[BR-SD] CFTV LONGOS - PROBLEMAS EM GERAL",
     "** PARA DIRECIONAMENTO, PRENCHER O IC ... Ex.: LCB - SRV-CFTV-PIR01 ... **\r\n\r\n"
     "Descrição do problema: Duas cameras de CTFV estão com problema de conexão. Sendo elas: PR421  e PR420\r\n\r\n"
     "Nome do solicitante:Morais\r\nNome do ponto de imagem (nome da câmera): PR421  e PR420\r\n"
     "Código do equipamento: PR421  e PR420\r\n",
     "Piracicaba - Câmeras PR421/PR420 sem conexão"),
]


@pytest.mark.parametrize("cidade,short,desc,esperado", REAIS)
def test_titulo_padrao_com_incidentes_reais(cidade, short, desc, esperado):
    from backend.payload import build_title
    titulo, ok = build_title(cidade, short, desc, False)
    assert titulo == esperado and ok


def test_titulo_nao_reconhecido_fica_marcado():
    from backend.payload import build_title
    titulo, ok = build_title("Resende", "[CFTV] - Coisa estranha", "sem detalhes", False)
    assert titulo == "Resende - Coisa estranha" and not ok  # cidade na frente, mas avisa

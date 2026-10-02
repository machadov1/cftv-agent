"""ServiceNow fictício para testar o agent sem tocar no ambiente real (SERVICENOW_MOCK=true).

Cenários baseados nos casos descritos na skill operador-cftv.
"""

MOCK_INCIDENTS = {
    "INC9000001": {"short_description": "Câmera PIR064 sem imagem - tela preta",
                   "description": "Usina: Piracicaba. Câmera PIR064 com tela preta desde ontem."},
    "INC9000002": {"short_description": "Câmera 03SUC tela preta",
                   "description": "Pátio de Metálicos. Câmeras BMA-SUC-01 e 03SUC sem sinal."},
    "INC9000003": {"short_description": "Câmeras RES024 / RES025 sem conexão",
                   "description": "Solicitante informa que as câmeras do pátio DRC estão offline."},
    "INC9000004": {"short_description": "TAG LORA 808 com falha",
                   "description": "Tag fixo 808 não comunica. Piracicaba."},
    "INC9000005": {"short_description": "Câmera MDE-012 sem movimentação PTZ",
                   "description": "Monlevade, câmera não responde ao comando PTZ."},
    "INC9000006": {"short_description": "Câmera sem imagem no galpão",
                   "description": "Solicitante não informou a unidade nem o código da câmera."},
    "INC9000007": {"short_description": "Câmera com tela preta - Itatiaçu",
                   "description": "Minas de Serra Azul. Servidor 10.58.84.22."},
    "INC9000008": {"short_description": "Servidor não está comunicando com SCOM server",
                   "description": "Alert: failed to heartbeat on computer BBD-APP-CFTV02.Americas.mittalco.com"},
    "INC9000009": {"short_description": "Fibra rompida no trecho da portaria - JDF",
                   "description": "Rompimento de fibra, câmeras JDF offline."},
}

def list_queue():
    return [{"sys_id": f"mock-{n.lower()}", "number": n, "state": "1", **d} for n, d in MOCK_INCIDENTS.items()]

def get_incident(number: str):
    data = MOCK_INCIDENTS.get(number)
    if not data:
        return None
    return {"sys_id": f"mock-{number.lower()}", "number": number, "state": "1", **data}


# Estado simulado após "aprovar" em mock (memória do processo): permite testar a checagem de duplicidade
_APPLIED: dict[str, dict] = {}

def get_current(sys_id: str):
    return _APPLIED.get(sys_id, {"state": "1", "work_notes": ""})

def apply_patch(sys_id: str, fields: dict):
    cur = dict(get_current(sys_id))
    if "state" in fields:
        cur["state"] = fields["state"]
    if fields.get("work_notes"):
        cur["work_notes"] = (cur.get("work_notes") or "") + fields["work_notes"]
    _APPLIED[sys_id] = cur

from fastapi import APIRouter, HTTPException

from backend import digifort, servidores

router = APIRouter(prefix="/servidores", tags=["servidores"])


@router.get("/status")
def status():
    return servidores.status()


@router.get("/topologia")
def topologia():
    """Unidade -> servidores CFTV, direto da lista de servidores (sem rede)."""
    return {"unidades": servidores.topologia(), "digifort_configurado": digifort.configured()}


@router.get("/topologia/{ip}")
def topologia_servidor(ip: str, forcar: bool = False):
    """Câmeras e estado de um servidor da lista (Digifort, só leitura; cache de alguns minutos).
    Falha volta com tipo (credencial, timeout, rede, config, resposta) para o painel mostrar o motivo."""
    srv = servidores.servidor_cftv(ip)
    if not srv:
        raise HTTPException(status_code=404, detail="IP fora da lista de servidores CFTV")
    try:
        inv = digifort.inventario(ip, forcar=forcar)
    except digifort.DigifortError as e:
        return {"ip": ip, "servidor": srv["nome"], "ok": False, "tipo_erro": e.tipo, "erro": str(e), "cameras": [],
                "resumo": None}
    cams = inv["cameras"]
    resumo = {"total": len(cams),
              "desativadas": sum(c["active"] is False for c in cams),
              "sem_sinal": sum(c["active"] is not False and c["working"] is False for c in cams),
              "ok": sum(c["active"] is not False and c["working"] is True for c in cams)}
    return {"ip": ip, "servidor": srv["nome"], "ok": True, "tipo_erro": None, "erro": None, "lido_em": inv["lido_em"],
            "cameras": cams, "resumo": resumo}

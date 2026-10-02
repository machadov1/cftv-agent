from fastapi import APIRouter, HTTPException

from backend import digifort, servidores, topologia as topo

router = APIRouter(prefix="/servidores", tags=["servidores"])


@router.get("/status")
def status():
    return servidores.status()


@router.get("/topologia")
def topologia():
    """Unidade -> servidores CFTV, direto da lista de servidores (sem rede)."""
    return {"unidades": servidores.topologia(), "digifort_configurado": digifort.configured()}


@router.get("/topologia/mapa")
def topologia_mapa(forcar: bool = False):
    """Disponibilidade de todas as unidades e servidores (Digifort lido em paralelo, cache de 10 min). Só leitura."""
    return topo.ler_todos(forcar=forcar)


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


@router.get("/config")
def config_list():
    """Lista todos os servidores CFTV com IP, status de desabilitação e credencial customizada."""
    try:
        creds = digifort.cred_read()
    except Exception:
        creds = {}
    result = []
    for srv in servidores.topologia():
        for s in srv["servidores"]:
            if s["ip"]:
                result.append({
                    "ip": s["ip"],
                    "nome": s["nome"],
                    "unidade": srv["unidade"],
                    "disabled": servidores.is_disabled(s["ip"]),
                    "credencial_customizada": s["ip"] in creds
                })
    return {"servidores": result}


@router.post("/credencial/{ip}")
def credencial_set(ip: str, usuario: str, senha: str):
    """Define credencial customizada para um IP (sobrescreve a padrão do .env)."""
    if not servidores.servidor_cftv(ip):
        raise HTTPException(status_code=404, detail="IP não está na lista de servidores CFTV")
    digifort.cred_set(ip, usuario, senha)
    return {"ip": ip, "status": "credencial salva"}


@router.delete("/credencial/{ip}")
def credencial_delete(ip: str):
    """Remove credencial customizada (volta a usar a padrão do .env)."""
    if not servidores.servidor_cftv(ip):
        raise HTTPException(status_code=404, detail="IP não está na lista de servidores CFTV")
    digifort.cred_delete(ip)
    return {"ip": ip, "status": "credencial removida"}


@router.patch("/{ip}/desabilitar")
def desabilitar(ip: str, disabled: bool = True):
    """Ativa/desativa a visualização de um servidor no mapa de topologia."""
    if not servidores.servidor_cftv(ip):
        raise HTTPException(status_code=404, detail="IP não está na lista de servidores CFTV")
    servidores.set_disabled(ip, disabled)
    return {"ip": ip, "disabled": disabled, "status": "atualizado"}

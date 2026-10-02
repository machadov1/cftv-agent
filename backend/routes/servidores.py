from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import digifort, servidores, topologia as topo
from backend.config import config

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


class CredIn(BaseModel):
    usuario: str
    senha: str


class DesabIn(BaseModel):
    disabled: bool


def _cftv(ip: str) -> dict:
    srv = servidores.servidor_cftv(ip)
    if not srv:
        raise HTTPException(status_code=404, detail="IP não está na lista de servidores CFTV")
    return srv


def _estado(leitura: dict | None) -> dict:
    if not leitura:
        return {"ok": None, "tipo_erro": None, "erro": None, "cameras": None}
    if "cameras" in leitura:
        return {"ok": True, "tipo_erro": None, "erro": None, "cameras": len(leitura["cameras"])}
    return {"ok": False, "tipo_erro": leitura.get("tipo_erro"), "erro": leitura.get("erro"), "cameras": None}


@router.get("/config")
def config_list():
    """Servidores CFTV com IP: desabilitado?, credencial própria (só o usuário, nunca a senha) e resultado da última leitura."""
    creds, off = digifort.cred_read(), servidores.desabilitados()
    out = []
    for u in servidores.topologia():
        for s in u["servidores"]:
            if s["ip"]:
                out.append({"ip": s["ip"], "nome": s["nome"], "tipo": s["tipo"], "unidade": u["unidade"],
                            "disabled": s["ip"] in off, "usuario_proprio": (creds.get(s["ip"]) or {}).get("usuario"),
                            **_estado(topo.ultima_leitura(s["ip"]))})
    return {"servidores": out, "usuario_padrao": config.DIGIFORT_USER}


@router.post("/credencial/{ip}")
def credencial_set(ip: str, body: CredIn):
    """Grava a credencial própria do servidor (data/digifort_credenciais.json, fora do git) e já relê o servidor com ela."""
    _cftv(ip)
    if not body.usuario.strip() or not body.senha:
        raise HTTPException(status_code=422, detail="Informe usuário e senha")
    digifort.cred_set(ip, body.usuario.strip(), body.senha)
    return {"ip": ip, **_estado(topo.reler_servidor(ip))}


@router.delete("/credencial/{ip}")
def credencial_delete(ip: str):
    """Volta a usar a credencial padrão do .env e relê o servidor."""
    _cftv(ip)
    digifort.cred_delete(ip)
    return {"ip": ip, **_estado(topo.reler_servidor(ip))}


@router.post("/{ip}/reler")
def reler(ip: str):
    _cftv(ip)
    return {"ip": ip, **_estado(topo.reler_servidor(ip))}


@router.put("/{ip}/desabilitado")
def desabilitar(ip: str, body: DesabIn):
    """Esconde (ou volta a mostrar) o servidor no mapa de topologia; escondido não é lido no Digifort."""
    _cftv(ip)
    servidores.set_disabled(ip, body.disabled)
    return {"ip": ip, "disabled": body.disabled}

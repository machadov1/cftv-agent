"""Mapa de disponibilidade: unidade -> servidores -> câmeras, a partir da lista de servidores e do inventário do Digifort.

Disponibilidade = câmeras transmitindo / câmeras ativas (desativadas no cadastro não contam). Na unidade, a mesma câmera
em mais de um servidor (principal + reserva) conta uma vez, com o melhor estado entre as cópias.
"""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from backend import digifort, servidores
from backend.config import ROOT

PARALELO = 8  # servidores lidos ao mesmo tempo (um por vez por servidor)
CACHE_PATH = ROOT / "data" / "topologia_cache.json"  # última leitura de todos os servidores (fora do git)


def _pct(ok: int, ativas: int) -> float | None:
    return round(100 * ok / ativas, 1) if ativas else None


def resumo_cameras(cams: list[dict]) -> dict:
    ativas = [c for c in cams if c["active"] is not False]
    ok = sum(c["working"] is True for c in ativas)
    return {"total": len(cams), "ativas": len(ativas), "ok": ok,
            "sem_sinal": sum(c["working"] is False for c in ativas),
            "desativadas": len(cams) - len(ativas), "disponibilidade": _pct(ok, len(ativas))}


def resumir(unidades: list[dict], leituras: dict[str, dict]) -> list[dict]:
    """unidades: servidores.topologia(); leituras: ip -> {'cameras': [...], 'lido_em'} ou {'erro', 'tipo_erro'}."""
    out = []
    for u in unidades:
        melhores: dict[str, dict] = {}
        srv_out, respondendo, com_ip = [], 0, 0
        for s in u["servidores"]:
            item = {**s, "ok": None, "tipo_erro": None, "erro": None, "lido_em": None, "cameras": None, "reserva": False}
            leitura = leituras.get(s["ip"]) if s["ip"] else None
            if s["ip"]:
                com_ip += 1
            if leitura and "cameras" in leitura:
                respondendo += 1
                r = resumo_cameras(leitura["cameras"])
                item.update(ok=True, lido_em=leitura.get("lido_em"), cameras=r, reserva=r["total"] > 0 and r["ativas"] == 0)
                for c in leitura["cameras"]:
                    k = digifort._fold(c["nome"])
                    atual = melhores.get(k)
                    nota = (c["active"] is not False, c["working"] is True)
                    if atual is None or nota > (atual["active"] is not False, atual["working"] is True):
                        melhores[k] = c
            elif leitura:
                item.update(ok=False, tipo_erro=leitura.get("tipo_erro"), erro=leitura.get("erro"))
            srv_out.append(item)
        out.append({"unidade": u["unidade"], "servidores": srv_out, "servidores_total": com_ip,
                    "servidores_respondendo": respondendo, "cameras": resumo_cameras(list(melhores.values()))})
    return out


_snap_lock = threading.Lock()


def _snap_read() -> dict | None:
    """Última leitura salva: {'lido_em': epoch, 'leituras': {ip: ...}}. Não expira: só relê quando você pede."""
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data.get("leituras"), dict) else None
    except (OSError, ValueError):
        return None


def _snap_write(leituras: dict, lido_em: float) -> None:
    try:
        CACHE_PATH.write_text(json.dumps({"lido_em": lido_em, "leituras": leituras}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _ler(ip: str, forcar: bool) -> dict:
    try:
        inv = digifort.inventario(ip, forcar=forcar)
        return {"cameras": inv["cameras"], "lido_em": inv["lido_em"]}
    except digifort.DigifortError as e:
        return {"erro": str(e), "tipo_erro": e.tipo}


def _visiveis() -> list[dict]:
    """Unidades da lista sem os servidores desabilitados (unidade que fica vazia some do mapa)."""
    off = servidores.desabilitados()
    out = []
    for u in servidores.topologia():
        srv = [s for s in u["servidores"] if not (s["ip"] and s["ip"] in off)]
        if srv:
            out.append({**u, "servidores": srv})
    return out


def montar(leituras: dict, lido_em: float | None) -> dict:
    res = resumir(_visiveis(), leituras)
    todas = [u["cameras"] for u in res]
    ativas, ok = sum(c["ativas"] for c in todas), sum(c["ok"] for c in todas)
    return {"unidades": res, "digifort_configurado": digifort.configured(), "lido_em": lido_em,
            "geral": {"disponibilidade": _pct(ok, ativas), "ativas": ativas, "ok": ok,
                      "servidores_total": sum(u["servidores_total"] for u in res),
                      "servidores_respondendo": sum(u["servidores_respondendo"] for u in res)}}


def ler_todos(forcar: bool = False) -> dict:
    """Mapa resumido. Sem forcar devolve a última leitura salva (instantâneo, mesmo antiga); só lê o Digifort
    (8 servidores em paralelo) quando não há leitura salva ou com forcar=True."""
    snap = None if forcar else _snap_read()
    if snap:
        return montar(snap["leituras"], snap["lido_em"])
    ips = sorted({s["ip"] for u in _visiveis() for s in u["servidores"] if s["ip"]})
    leituras = {}
    if digifort.configured() and ips:
        with ThreadPoolExecutor(max_workers=PARALELO) as ex:
            leituras = dict(zip(ips, ex.map(lambda ip: _ler(ip, forcar), ips)))
    agora = time.time()
    with _snap_lock:
        _snap_write(leituras, agora)
    return montar(leituras, agora)


def reler_servidor(ip: str) -> dict:
    """Relê um servidor (ex.: depois de trocar a senha) e atualiza só ele na leitura salva."""
    leitura = _ler(ip, True)
    with _snap_lock:
        snap = _snap_read() or {"lido_em": time.time(), "leituras": {}}
        snap["leituras"][ip] = leitura
        _snap_write(snap["leituras"], snap["lido_em"])
    return leitura


def ultima_leitura(ip: str) -> dict | None:
    return ((_snap_read() or {}).get("leituras") or {}).get(ip)

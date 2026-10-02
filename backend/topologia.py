"""Mapa de disponibilidade: unidade -> servidores -> câmeras, a partir da lista de servidores e do inventário do Digifort.

Disponibilidade = câmeras transmitindo / câmeras ativas (desativadas no cadastro não contam). Na unidade, a mesma câmera
em mais de um servidor (principal + reserva) conta uma vez, com o melhor estado entre as cópias.
"""
from concurrent.futures import ThreadPoolExecutor

from backend import digifort, servidores

PARALELO = 8  # servidores lidos ao mesmo tempo (um por vez por servidor)


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


def ler_todos(forcar: bool = False) -> dict:
    """Lê (em paralelo, com o cache do inventário) todos os servidores CFTV com IP e devolve o mapa resumido."""
    unidades = servidores.topologia()
    ips = sorted({s["ip"] for u in unidades for s in u["servidores"] if s["ip"]})

    def ler(ip):
        try:
            inv = digifort.inventario(ip, forcar=forcar)
            return ip, {"cameras": inv["cameras"], "lido_em": inv["lido_em"]}
        except digifort.DigifortError as e:
            return ip, {"erro": str(e), "tipo_erro": e.tipo}

    leituras = {}
    if digifort.configured() and ips:
        with ThreadPoolExecutor(max_workers=PARALELO) as ex:
            leituras = dict(ex.map(ler, ips))
    res = resumir(unidades, leituras)
    todas = [u["cameras"] for u in res]
    ativas, ok = sum(c["ativas"] for c in todas), sum(c["ok"] for c in todas)
    return {"unidades": res, "digifort_configurado": digifort.configured(),
            "geral": {"disponibilidade": _pct(ok, ativas), "ativas": ativas, "ok": ok,
                      "servidores_total": sum(u["servidores_total"] for u in res),
                      "servidores_respondendo": sum(u["servidores_respondendo"] for u in res)}}

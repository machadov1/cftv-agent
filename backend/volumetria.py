"""Volumetria mensal (entraram x encerrados) de incidentes e TASKs de acesso. Só leitura: API de estatísticas do SN."""
import time
from datetime import date, datetime

from backend import filas
from backend.backlog import _TZ
from backend.config import config
from backend.servicenow_api import sn_api, _check

MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
CACHE_TTL = 600
_cache: dict = {}


def meses(hoje: date, n: int = 5) -> list[tuple[str, date, date]]:
    """Os n meses até o atual (inclusive): (rótulo 'out/26', 1º dia, 1º dia do mês seguinte)."""
    out = []
    a, m = hoje.year, hoje.month
    for _ in range(n):
        ini = date(a, m, 1)
        fim = date(a + (m == 12), m % 12 + 1, 1)
        out.append((f"{MESES[m - 1]}/{a % 100:02d}", ini, fim))
        a, m = (a - 1, 12) if m == 1 else (a, m - 1)
    return out[::-1]


def _entre(campo: str, ini: date, fim: date) -> str:
    return (f"{campo}>=javascript:gs.dateGenerate('{ini}','00:00:00')"
            f"^{campo}<javascript:gs.dateGenerate('{fim}','00:00:00')")


def _contar(tabela: str, query: str) -> int:
    http, headers = sn_api._client()
    resp = http.get(f"{sn_api.base_url}/api/now/stats/{tabela}", headers=headers, timeout=30,
                    params={"sysparm_count": "true", "sysparm_query": query})
    _check(resp)
    return int(resp.json()["result"]["stats"]["count"])


def _consultas(tipo: str) -> tuple[str, tuple[str, str], tuple[str, str]]:
    """(tabela, (filtro, campo) de entrada, (filtro, campo) de encerramento)."""
    if tipo == "tasks":
        from backend.tasks import GRUPOS, CAT_ITEMS
        base = f"{GRUPOS}^request_item.cat_itemIN{','.join(CAT_ITEMS)}"
        return "sc_task", (base, "opened_at"), (f"{base}^stateIN3,4", "closed_at")
    # incidentes: entrada pelo filtro do board; encerrados = relatório "Incidentes Encerrados no Mês" (resolved_at)
    return "incident", (filas.grupos_query(), "opened_at"), (filas.grupos_query_encerrados(), "resolved_at")


def serie(tipo: str, n: int = 5, force: bool = False) -> dict:
    chave = (tipo, n)
    hit = _cache.get(chave)
    if hit and not force and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    agora = datetime.now(_TZ)
    tabela, (q_in, c_in), (q_out, c_out) = _consultas(tipo)
    pontos = []
    for i, (rotulo, ini, fim) in enumerate(meses(agora.date(), n)):
        if config.SERVICENOW_MOCK:
            entraram, encerrados = 20 + 3 * i, 18 + 2 * i
        else:
            entraram = _contar(tabela, f"{q_in}^{_entre(c_in, ini, fim)}")
            encerrados = _contar(tabela, f"{q_out}^{_entre(c_out, ini, fim)}")
        pontos.append({"mes": rotulo, "inicio": ini.isoformat(), "entraram": entraram, "encerrados": encerrados})
    data = {"tipo": tipo, "atualizado_em": agora.isoformat(), "meses": pontos,
            "total_encerrados": sum(p["encerrados"] for p in pontos),
            "total_entraram": sum(p["entraram"] for p in pontos)}
    _cache[chave] = (time.time(), data)
    return data

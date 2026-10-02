"""Filas acompanhadas pelo Painel: lidas de data/filas.json (fonte: board 'Incidentes - CFTV/A4')."""
import json
from functools import lru_cache

from backend.config import ROOT

PATH = ROOT / "data" / "filas.json"


@lru_cache(maxsize=1)
def _cfg() -> dict:
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


def reload() -> None:
    _cfg.cache_clear()


def grupos_query() -> str:
    """Trecho do encoded query com as filas (OR entre elas), idêntico ao filtro do board do ServiceNow."""
    f = _cfg()["filtro"]
    parts = [f"assignment_group.nameSTARTSWITH{p}" for p in f["comeca_com"]]
    parts += [f"assignment_group.nameLIKE{p}" for p in f["contem"]]
    return "^OR".join(parts)


def grupos_query_encerrados() -> str:
    """Filtro de grupos do relatório 'Incidentes Encerrados no Mês' do painel (não inclui a fila PEC)."""
    f = _cfg()["filtro_encerrados_mes"]
    parts = [f"assignment_group.nameSTARTSWITH{p}" for p in f["comeca_com"]]
    parts += [f"assignment_group.nameLIKE{p}" for p in f["contem"]]
    return "^OR".join(parts)


def estados_fora() -> str:
    return ",".join(str(s) for s in _cfg()["filtro"]["estados_fora"])


def equipes() -> list[str]:
    return [e["sigla"] for e in _cfg()["equipes"]] + [_cfg()["outras"]]


def team_of(group: str | None) -> str:
    """Sigla da equipe: nome exato do grupo primeiro, depois prefixo; o resto cai em 'Outras'."""
    g = (group or "").strip()
    for e in _cfg()["equipes"]:
        if g in e.get("grupos", []):
            return e["sigla"]
    for e in _cfg()["equipes"]:
        if any(g.startswith(p) for p in e.get("prefixos", [])):
            return e["sigla"]
    return _cfg()["outras"]

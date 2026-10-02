"""Pistas de localidade fora do texto: IC afetado (nome = servidor, localização do IC) e localização do solicitante.

Cada pista diz de onde veio, o valor lido e a unidade que indica. O motor de regras usa a mais forte e baixa a
confiança quando duas apontam unidades diferentes. Funções puras (o incidente já vem lido do ServiceNow).
"""
import json
import re
import unicodedata

from backend.config import ROOT
from backend.scom import HOST_PREFIXO, extract_host, host_do_ci, is_auto_alert, unidade_do_host

PESO_HOST = 100   # alerta automático: o servidor citado define a fila (decisão do Victor, 01/10)
PESO_IC = 80      # IC afetado é servidor de uma unidade
PESO_LOCAL = 75   # localização do IC / do solicitante
_unidades: list[tuple[str, str]] | None = None
_ics: dict[str, str] | None = None


def _fold(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _nomes_unidade() -> list[tuple[str, str]]:
    """[(nome sem acento, unidade)] das unidades CFTV (sem LORA/Projects), nomes mais longos primeiro."""
    global _unidades
    if _unidades is None:
        mapa = json.loads((ROOT / "data" / "mapeamentos.json").read_text(encoding="utf-8"))
        pares = set()
        for unidade, m in mapa.items():
            if "LORA" in unidade or (isinstance(m, dict) and m.get("alerta")):
                continue
            for nome in (unidade, m.get("cidade") if isinstance(m, dict) else None):
                if nome and len(nome) >= 4:
                    pares.add((_fold(nome), unidade))
        _unidades = sorted(pares, key=lambda p: -len(p[0]))
    return _unidades


def _ic_por_nome() -> dict[str, str]:
    """IC padrão de cada unidade no mapeamento ('LCB-SRV-CFTV-BMA01' -> 'Barra Mansa'), sem espaços."""
    global _ics
    if _ics is None:
        mapa = json.loads((ROOT / "data" / "mapeamentos.json").read_text(encoding="utf-8"))
        _ics = {re.sub(r"\s", "", m["ic_nome"]).upper(): u for u, m in mapa.items()
                if isinstance(m, dict) and m.get("ic_nome") and "LORA" not in u}
    return _ics


def unidade_do_ic(ci_nome: str | None) -> tuple[str | None, str | None]:
    """(nome curto, unidade) do IC afetado: servidor da lista/prefixo (PRJ-APP-CFTV02), IC padrão da unidade
    (LCB-SRV-CFTV-BMA01) ou sigla no fim do nome (SRV-CFTV-GUA)."""
    host = host_do_ci(ci_nome)
    if not host:
        return None, None
    unidade = unidade_do_host(host) or _ic_por_nome().get(re.sub(r"\s", "", ci_nome or "").upper())
    if not unidade:
        sigla = re.sub(r"\d+$", "", host.split("-")[-1])
        unidade = HOST_PREFIXO.get(sigla) if sigla != "PRJ" else None
    return host, unidade


def unidade_do_local(texto: str | None) -> str | None:
    """'Longos - USINA PIRACICABA' -> 'Piracicaba'. Nome de unidade contido no texto da localização."""
    t = _fold(texto)
    if not t:
        return None
    for nome, unidade in _nomes_unidade():
        if nome in t:
            return unidade
    return None


def coletar(inc: dict) -> list[dict]:
    """Pistas do incidente: [{fonte, valor, unidade, peso}]. Só fontes com unidade reconhecida entram."""
    short, desc = inc.get("short_description") or "", inc.get("description") or ""
    alerta = is_auto_alert(short, desc, inc.get("caller_id") or "")
    out = []

    host_txt = extract_host(short, desc)
    candidatos = [("host do alerta", host_txt, unidade_do_host(host_txt))] if host_txt else []
    candidatos.append(("IC afetado", *unidade_do_ic(inc.get("cmdb_ci"))))
    for fonte, host, unidade in candidatos:
        if host and unidade:
            out.append({"fonte": fonte, "valor": host, "unidade": unidade,
                        "peso": PESO_HOST if alerta else PESO_IC})
            break  # o host do texto e o do IC costumam ser o mesmo: basta um

    for fonte, campo in (("local do IC", "cmdb_ci_location"), ("local do solicitante", "caller_location")):
        unidade = unidade_do_local(inc.get(campo))
        if unidade:
            out.append({"fonte": fonte, "valor": inc.get(campo), "unidade": unidade, "peso": PESO_LOCAL})
    return out


def melhor(pistas: list[dict]) -> dict | None:
    return max(pistas, key=lambda p: p["peso"], default=None)


def conflitos(pistas: list[dict], localidade: str | None) -> list[dict]:
    """Pistas que apontam para outra unidade (ignora LORA/Projects x unidade do mesmo host, já decididos pelo host)."""
    if not localidade:
        return []
    base = localidade.replace(" (LORA)", "")
    return [p for p in pistas if p["unidade"] != base and p["unidade"] != localidade]

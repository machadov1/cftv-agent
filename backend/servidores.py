"""Lista de servidores (export de 'Gestão De Servidores'): só colunas não sensíveis, nunca senhas/chaves."""
import csv
import re
import unicodedata

from backend.config import ROOT

PATH = ROOT / "data" / "servidores.csv"

# Lista branca: única coisa que sai do arquivo. Senhas, usuários, iLO, Digifort, hardkeys e links ficam de fora.
CAMPOS = {
    "unidade": "Unidade",
    "cliente": "Cliente",
    "nome": "Nome Do Ativo",
    "ip": "IP",
    "ip_ilo": "IP da iLO",
    "tipo": "Tipo de Ativo",
    "dominio": "Domínio ArcelorMittal ?",
    "hyperv": "Hyper-V + VM",
    "responsavel": "EMP. Responsável",
    "modelo": "Modelo do Ativo",
    "so": "Versão S.O",
    "preventiva": "Próxima Preventiva",
    "obs": "Observações Gerais",
    "obs_vm": "Observações VM",
}

_IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_HOST_LIKE = re.compile(r"\b[A-Za-z]{2,4}-(?:APP|PRD|SRV|WEB|DB)-[A-Za-z0-9]+\b", re.IGNORECASE)

_cache = {"mtime": None, "rows": []}


def _clean(v) -> str | None:
    v = (v or "").strip()
    return None if v in ("", "-", "N/A") else v


def _load() -> list[dict]:
    if not PATH.exists():
        _cache.update(mtime=None, rows=[])
        return []
    mtime = PATH.stat().st_mtime
    if _cache["mtime"] == mtime:
        return _cache["rows"]
    rows = []
    with open(PATH, encoding="utf-8-sig", newline="") as f:
        for raw in csv.DictReader(f):
            norm = {(k or "").strip(): v for k, v in raw.items()}  # cabeçalhos vêm com espaço no fim
            row = {campo: _clean(norm.get(coluna)) for campo, coluna in CAMPOS.items()}
            if row["nome"]:
                rows.append(row)
    _cache.update(mtime=mtime, rows=rows)
    return rows


def status() -> dict:
    rows = _load()
    return {"carregado": bool(rows), "total": len(rows)}


def find(query: str) -> dict | None:
    """Busca por nome do ativo (sem diferenciar maiúsculas) ou por IP (servidor ou iLO)."""
    q = (query or "").strip()
    if not q:
        return None
    for r in _load():
        if r["nome"].lower() == q.lower():
            return r
    if _IP_RE.match(q):
        for r in _load():
            if q in (r["ip"], r["ip_ilo"]):
                return r
    return None


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s*\(.*?\)|[^a-z0-9]+", " ", s).strip()


def cftv_da_unidade(localidade: str | None) -> list[dict]:
    """Servidores de CFTV (Digifort) da unidade, com IP: principais primeiro, VMs depois, failover por último."""
    alvo = _fold(localidade or "")
    if not alvo:
        return []
    ordem = {"servidor": 0, "maquina": 1, "faillover": 2, "failover": 2}
    achados = [r for r in _load() if r["ip"] and "cftv" in (r["tipo"] or "").lower()
               and (_fold(r["unidade"] or "") == alvo or alvo in _fold(r["unidade"] or ""))]
    return sorted(achados, key=lambda r: ordem.get(_fold(r["tipo"]).split(" ")[0], 3))


def detect(*texts: str) -> dict | None:
    """Acha um servidor citado no texto: primeiro nomes da lista, depois padrão de hostname (XXX-APP-CFTV02)."""
    text = " ".join(t or "" for t in texts)
    low = text.lower()
    for r in _load():
        nome = r["nome"]
        if len(nome) >= 4 and re.search(rf"(?<![A-Za-z0-9_-]){re.escape(nome.lower())}(?![A-Za-z0-9_-])", low):
            return r
    m = _HOST_LIKE.search(text)
    if m:
        return find(m.group(0)) or {"nome": m.group(0).upper(), "ip": None}
    return None

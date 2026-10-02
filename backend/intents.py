"""Roteador local de atalhos no agente de chat: frases naturais → ações diretas (sem LLM).

Reconhece: "trate os novos de Piracicaba", "/fila pir vencem hoje", "consulte INC4003560 para onde vai", etc.
Retorna template pré-montado com `via: "atalho"` marcado no histórico. Se não reconhece, cai no LLM normal.
"""
import re
from typing import Optional

from backend import backlog
from backend.filas import team_of, equipes, grupos_query
from backend.rules_engine import engine

# Frases que disparam cada intenção (ordem importa: mais específico primeiro)
PATTERNS = {
    "tratar": [
        r"^tr[ae]t(ar?|e|ando)(\s+[oi]s)?\s+(novos?|new)",  # "tratar novos", "tratando novo", "trate o novo"
        r"^tr[ae]t(ar?|e|ando)(\s+[oi]s)?(\s+(os\s+)?incidentes?)?",  # "tratar incidentes", "tratar INC123"
        r"^despacha(r?|ndo)?(\s+[oi]s)?(\s+(os\s+)?incidentes?)?",  # "despachar", "despachar incidentes"
    ],
    "fila": [
        r"fila",  # "fila de X", "fila lora", etc. (mais geral)
        r"(quais?|quantos).*(incidente|tic)",  # "quais incidentes", "quantos tics", "quais incidentes PIR"
    ],
    "consultar": [
        r"consult",  # "consulta", "consultar", "consultation"
        r"(onde.*)?vai",  # "para onde vai", "onde vai", "vai"
    ],
    "ajuda": [
        r"^(ajuda|help|\?|/ajuda|/help)",  # "/ajuda", "?"
    ],
}

# Cidades/siglas resolvidas pelos padrões do rules.json + filas
LOCALIDADES_MAP = {
    r"(?<![a-z])(pir|piraca|piracicaba)(?![a-z])": "Piracicaba",
    r"(?<![a-z])(mde|monlevade|joão)(?![a-z])": "João Monlevade",
    r"(?<![a-z])(bm|bma|barra|mansa)(?![a-z])": "Barra Mansa",
    r"(?<![a-z])(rsd|res|resende)(?![a-z])": "Resende",
    r"(?<![a-z])(jdf|juiz|fora)(?![a-z])": "Juiz de Fora",
    r"(?<![a-z])(bbd|bauru)(?![a-z])": "Bauru",
    r"(?<![a-z])(sab|sabará)(?![a-z])": "Sabará",
    r"(?<![a-z])(gua|guarulhos)(?![a-z])": "Guarulhos",
    r"lora": "Piracicaba (LORA)",  # Atalho: LORA → PIR por padrão
}

INC_PATTERN = re.compile(r"\b(INC\d{6,8})\b", re.IGNORECASE)
ESTADO_MAP = {
    r"novo|new": "Novo",
    r"em\s+andamento|progress|em_andamento|andamento": "Em Andamento",
}
PRAZO_MAP = {
    r"(vence\s+)?hoje|today|due_today": "hoje",
    r"(vence\s+)?(amanha|amanh[ae]|tomorrow)": "amanhã",
    r"(vencidos?|overdue|atrasados?)": "vencidos",
    r"sla(\s+)?(violado|breach|violated)": "sla_violado",
}

def _match_intent(text: str) -> Optional[str]:
    """Retorna a intenção (tratar, fila, consultar, ajuda) ou None."""
    lower = text.lower().strip()
    for intent, pats in PATTERNS.items():
        for pat in pats:
            if re.search(pat, lower):
                return intent
    return None

def _extract_localidades(text: str) -> list[str]:
    """Extrai cidades/siglas do texto."""
    results = []
    lower = text.lower()
    for pat, localidade in LOCALIDADES_MAP.items():
        if re.search(pat, lower):
            results.append(localidade)
    return list(dict.fromkeys(results))  # Remove dups, mantém ordem

def _extract_incidentes(text: str) -> list[str]:
    """Extrai números INC do texto."""
    return [m.group(1).upper() for m in INC_PATTERN.finditer(text)]

def _extract_estado(text: str) -> Optional[str]:
    """Extrai estado (Novo, Em Andamento) do texto."""
    lower = text.lower()
    for pat, estado in ESTADO_MAP.items():
        if re.search(pat, lower):
            return estado
    return None

def _extract_prazo(text: str) -> Optional[str]:
    """Extrai prazo (hoje, amanhã, vencidos, sla_violado) do texto."""
    lower = text.lower()
    for pat, prazo in PRAZO_MAP.items():
        if re.search(pat, lower):
            return prazo
    return None

def resolve_tratar(text: str) -> dict:
    """Intenção 'tratar': encontra incidentes novos (ou especificados) para despachar."""
    nums = _extract_incidentes(text)
    locs = _extract_localidades(text)
    estado = _extract_estado(text) or "Novo"

    if not locs and "novo" not in text.lower() and not nums:
        return None  # Ambíguo

    # Se números foram dados, propõe direto
    if nums:
        return {"acao": "propor", "numeros": nums}

    # Se localidade + estado, lista e propõe
    if locs:
        localidade = locs[0] if len(locs) == 1 else None
        if len(locs) > 1:
            return None  # Ambíguo
        return {"acao": "listar_e_propor", "localidade": localidade, "estado": estado}

    # Se só "novos" (sem localidade), lista Geral
    return {"acao": "listar_e_propor", "estado": estado}

def resolve_fila(text: str) -> dict:
    """Intenção 'fila': lista incidentes de uma fila/equipe/localidade por estado ou prazo."""
    locs = _extract_localidades(text)
    estado = _extract_estado(text)
    prazo = _extract_prazo(text)

    # Extrai equipe por sigla explícita (PIR, MDE, LORA...)
    equipe = None
    for e in equipes():
        if re.search(rf"(?<![a-z]){re.escape(e)}(?![a-z])", text, re.I):
            equipe = e
            break

    localidade = locs[0] if locs and len(locs) == 1 else None

    return {"acao": "listar_fila", "localidade": localidade, "equipe": equipe, "estado": estado, "prazo": prazo}

def resolve_consultar(text: str) -> dict:
    """Intenção 'consultar': lê um ou mais incidentes e responde com destino."""
    nums = _extract_incidentes(text)
    if not nums:
        return None
    return {"acao": "consultar", "numeros": nums}

def resolve_ajuda(text: str) -> dict:
    """Intenção 'ajuda': mostra atalhos disponíveis."""
    return {"acao": "ajuda"}

def run(text: str) -> Optional[dict]:
    """Roteador principal: tenta resolver a intenção localmente (sem LLM).

    Retorna: {
      "via": "atalho",
      "acao": "listar_e_propor" | "consultar" | "listar_fila" | "ajuda",
      ... (parâmetros específicos da ação)
    }
    ou None se não reconhecer.
    """
    intent = _match_intent(text)
    if not intent:
        return None

    result = None
    if intent == "tratar":
        result = resolve_tratar(text)
    elif intent == "fila":
        result = resolve_fila(text)
    elif intent == "consultar":
        result = resolve_consultar(text)
    elif intent == "ajuda":
        result = resolve_ajuda(text)

    if result:
        result["via"] = "atalho"
    return result

"""Chamadas ao LLM apenas para edge cases (~10-20% dos incidentes). Provedores em backend/llm.py."""
from backend import llm

LOCALIDADES_PADRAO = ["Piracicaba", "João Monlevade", "Resende", "Juiz de Fora",
                      "Bauru", "Barra Mansa", "Sabará", "Guarulhos", "Candeias",
                      "Iracemápolis", "Jaboatão"]

def _complete(prompt: str, max_tokens: int) -> str:
    # Provedores e fallback em data/llm.json (9router, OpenRouter...). Folga de tokens: modelos com raciocínio gastam antes de responder.
    return llm.complete(prompt, max_tokens=max(max_tokens, 400))

def call_claude_for_localidade(description: str, opcoes: list[str] | None = None) -> str | None:
    """Identifica localidade quando as regras não casam. None se desconhecida."""
    opcoes = opcoes or LOCALIDADES_PADRAO
    answer = _complete(
        "Identifique a localidade dessa descrição de incidente.\n"
        "Responda com APENAS o nome da cidade, ou 'desconhecida'.\n\n"
        f"Descrição: {description}\n\n"
        f"Opções válidas: {', '.join(opcoes)}.",
        max_tokens=30,
    )
    answer = answer.strip().strip(".").strip()
    for opcao in opcoes:
        if opcao.lower() == answer.lower():
            return opcao
    return None

def call_claude_for_ritm(description: str, localidade: str) -> bool:
    """Decide se precisa RITM quando há dúvida"""
    answer = _complete(
        f"Incidente: {description}\nLocalidade: {localidade}\n\n"
        "Precisa de RITM? Responda SIM ou NÃO.",
        max_tokens=10,
    )
    return "SIM" in answer.upper()

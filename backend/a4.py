"""Reconhecimento de chamados A4 (UWB, automação, RFID, 4 Olhos, LORA)."""
import re
import unicodedata
from typing import Optional


def _norm(s: str) -> str:
    """Remove acentos e converte para minúsculas."""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower().strip()

# Padrões A4 (UWB, Smart Safety, Safe Zone, RFID empilhadeira, 4 Olhos, analítico) — SEM LORA
_PATTERNS = {
    "UWB": r"\bUWB\b|portal.*UWB",
    "Smart Safety": r"smart\s*safety|(?:WUB|dispositivo\s+WUB).*(?:empilh|sensor)",
    "Safe Zone": r"safe\s*zone",
    "Passagem Segura": r"passagem\s+segura",
    "Portaria Inteligente": r"portaria\s+inteligente|portaria\s+automática",
    "Bracelete": r"bracelete",
    "RFID Empilhadeira": r"(?:RFID|sensor).*empilh|empilh.*(?:RFID|sensor|UWB|defeito|falha|parado)",
    "Core/Sensor": r"\bcore\s+(?:central|empilh|sensor)|sensor\s+(?:UWB|empilh)",
    "4 Olhos": r"4\s*olhos|jetson\s*nano",
    "Analítico": r"analitico\s+(?:do|da)\s+(?:alto\s+forno|aciaria)|(?:alto\s+forno|aciaria).*analitico.*emis",
}

_COMPILED = {k: re.compile(v, re.IGNORECASE) for k, v in _PATTERNS.items()}


def is_a4(short_description: str, description: str = "", cmdb_ci: str = "") -> tuple[bool, Optional[str]]:
    """
    Detecta se um incidente é A4 (UWB/automação/RFID/4Olhos/LORA/analítico).
    Retorna (é_a4: bool, sistema: str|None).
    """
    texto = _norm(f"{short_description} {description} {cmdb_ci}")

    for sistema, pattern in _COMPILED.items():
        if pattern.search(texto):
            return True, sistema

    return False, None


def titulo(short_description: str, description: str, sigla_unidade: str) -> str:
    """Monta título padrão A4: '{SIGLA} A4 - {descrição}'. Trata título vazio com fallback em description."""
    desc = short_description.strip()
    # Remove "EQUIPE MDE A4 - " ou "JDF A4 - " se já houver
    desc = re.sub(r"^(EQUIPE\s+)?[A-Z]{2,}\s+A4\s*-\s*", "", desc, flags=re.IGNORECASE).strip()
    # Se vazio ou genérico, tira da description
    if not desc or "[" in desc or len(desc) < 10:
        # Busca a 1ª frase substantiva de description
        frase = re.split(r'\.\s|,\s|\n', (description or "").strip())[0][:80]
        desc = desc or frase or "Incidente A4"
    return f"{sigla_unidade} A4 - {desc}"


def fila_a4_para_unidade(unidade: str) -> Optional[tuple[str, str]]:
    """Retorna (fila, grupo_sys_id) da A4 para uma unidade, ex.: 'João Monlevade' -> ('AMS-TI-A4-MDE', 'abc123').
    Usa sigla: 'Monlevade' → 'MDE'; unidade sem fila A4 = (None, None)."""
    import json
    try:
        filas = json.load(open("data/a4_queues.json", encoding="utf-8"))["filas_a4"]
        # Tentar sigla (se unidade é uma sigla exata como 'MDE')
        for fila, info in filas.items():
            if info.get("sigla", "").lower() == unidade.lower() and info["ativo"]:
                return fila, info.get("grupo")
        # Tentar substring (se unidade é o nome completo como 'João Monlevade')
        for fila, info in filas.items():
            if unidade.lower() in info.get("unidade", "").lower() and info["ativo"]:
                return fila, info.get("grupo")
    except (FileNotFoundError, KeyError):
        pass
    return None, None


def saudacao(hora: int) -> str:
    return "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite"


def email_a4(incident_number: str, unidade: str, descricao: str, caller: str = "", email: str = "",
             sla: str = "", hora: int | None = None) -> dict:
    """Rascunho do e-mail A4 (modelo do .oft em data/a4_queues.json): {para, cc, assunto, corpo, mailto}.
    Nunca envia: o painel abre o app de e-mail padrão com tudo preenchido para o Victor revisar."""
    import json
    from datetime import datetime
    from urllib.parse import quote
    from backend.config import ROOT

    t = json.loads((ROOT / "data" / "a4_queues.json").read_text(encoding="utf-8")).get("email_template", {})
    campos = {"{INCIDENT}": incident_number, "{LOCALIDADE}": unidade or "", "{UNIDADE}": unidade or "",
              "{DESCRICAO}": (descricao or "").strip(), "{SOLICITANTE}": caller or "", "{EMAIL}": email or "",
              "{SLA}": sla or "", "{SAUDACAO}": saudacao(datetime.now().hour if hora is None else hora)}

    def preencher(texto: str) -> str:
        for k, v in campos.items():
            texto = texto.replace(k, v)
        return texto

    corpo = t.get("corpo", "")
    corpo = preencher("\n".join(corpo) if isinstance(corpo, list) else corpo)
    assunto = preencher(t.get("assunto", "")).replace(" ()", "")  # sem unidade: sem parênteses vazios
    out = {"para": t.get("para", ""), "cc": t.get("cc", ""), "assunto": assunto, "corpo": corpo}
    out["mailto"] = (f"mailto:{quote(out['para'], safe='@,')}?cc={quote(out['cc'], safe='@,')}"
                     f"&subject={quote(out['assunto'])}&body={quote(corpo.replace(chr(10), chr(13) + chr(10)))}")
    return out

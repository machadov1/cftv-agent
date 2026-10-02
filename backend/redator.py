"""Redator de textos com IA (9router): transforma o rascunho do Victor no padrão do manual de encerramento.

Só redige. Nunca grava nada no ServiceNow: o texto volta para o painel, que continua editável e passa pelo mesmo envio
(revisão + segurar). O manual inteiro vai como instrução; os comandos rápidos do manual viram botões.
"""
import re

from backend import llm, textos
from backend.config import ROOT

_manual = {"mtime": None, "texto": ""}


def manual() -> str:
    path = ROOT / textos.MANUAL
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return ""
    if _manual["mtime"] != mtime:
        _manual.update(mtime=mtime, texto=path.read_text(encoding="utf-8"))
    return _manual["texto"]


COMANDOS = {
    "enche": "Comando 'enche': adicione Análise e detalhe a Resolução, sem inventar fato novo.",
    "enxuto": "Comando 'enxuto': corte para Causa raiz + Resolução + Encerramento, frases mínimas.",
    "humanizada": "Comando 'humanizada': gere a mensagem de Teams/WhatsApp ao solicitante no padrão do manual "
                  "(saudação pelo período, só o primeiro nome, sem jargão de ServiceNow), não o texto de encerramento.",
    "sem_req": "Comando 'sem req': remova a RITM e use o fechamento 'Incidente encerrado.'.",
    "faz_um_pra_cada": "Comando 'faz um pra cada': um encerramento por item (câmera, incidente, servidor), separados por "
                       "uma linha com ---.",
    "junta": "Comando 'junta': una os textos em uma resposta só.",
}

_REGRAS_SAIDA = """
Formato da sua resposta (obrigatório):
- Só o texto final, pronto para colar no ServiceNow (ou a mensagem, no comando humanizada). Texto plano: sem markdown,
  sem negrito, sem cercas de código, sem comentário antes ou depois.
- Se faltar informação que impede escrever (a tratativa não foi informada, NTFS/CPU sem hostname, termo ambíguo que muda
  o texto), responda com UMA linha: "PERGUNTA: <pergunta curta>".
- Se escreveu mas falta algo (RITM em caso pendente, inconsistência no relato, risco), acrescente no fim uma linha
  "AVISO: <uma frase>". O que faltar no texto fica entre colchetes, ex.: [RITM].
- Use só fatos do rascunho e dos dados do incidente. Nunca invente ação, horário, nome ou número.
"""


def _sistema() -> str:
    return ("Você redige os textos de incidentes do Victor (CFTV, LORA, UWB) seguindo à risca o manual abaixo.\n\n"
            + manual() + "\n" + _REGRAS_SAIDA)


def _usuario(dados: dict, rascunho: str, comando: str | None, texto_atual: str | None) -> str:
    linhas = ["Dados do incidente (do sistema, confiáveis):"]
    for rot, k in (("Incidente", "incident_number"), ("Solicitante (primeiro nome)", "solicitante"),
                   ("Saudação pelo horário de agora (use esta)", "saudacao"),
                   ("Título", "titulo"), ("Unidade", "localidade"),
                   ("Câmeras", "cameras"), ("Servidor", "host"), ("RITM", "ritm"), ("Cenário", "cenario")):
        if dados.get(k):
            linhas.append(f"- {rot}: {dados[k]}")
    if dados.get("descricao"):
        linhas.append(f"- Descrição do solicitante: {dados['descricao'][:700]}")
    if dados.get("modelo"):
        linhas += ["", "Modelo que o sistema montou para o cenário (base, ajuste ao rascunho):", dados["modelo"]]
    if texto_atual:
        linhas += ["", "Texto atual (refaça a partir dele):", texto_atual]
    linhas += ["", "Rascunho do Victor (o que foi feito / o que ele quer):", rascunho.strip() or "(sem rascunho)"]
    if comando:
        linhas += ["", COMANDOS[comando]]
    return "\n".join(linhas)


def _limpar(t: str) -> str:
    t = re.sub(r"^```\w*\s*|\s*```$", "", (t or "").strip())
    return t.replace("**", "").strip()


def redigir(dados: dict, rascunho: str, comando: str | None = None, texto_atual: str | None = None) -> dict:
    """{texto, avisos} ou {pergunta}. Levanta llm.LLMError se o 9router não responder."""
    if comando and comando not in COMANDOS:
        raise ValueError(f"Comando desconhecido: {comando}")
    r = llm.chat([{"role": "system", "content": _sistema()},
                  {"role": "user", "content": _usuario(dados, rascunho, comando, texto_atual)}], max_tokens=900)
    bruto = _limpar((r.get("message") or {}).get("content") or "")
    if not bruto:
        raise llm.LLMError("O modelo devolveu texto vazio")
    if bruto.upper().startswith("PERGUNTA:"):
        return {"pergunta": bruto.split(":", 1)[1].strip(), "modelo": r.get("model")}
    avisos_ia = [l.split(":", 1)[1].strip() for l in bruto.splitlines() if l.strip().upper().startswith("AVISO:")]
    texto = "\n".join(l for l in bruto.splitlines() if not l.strip().upper().startswith("AVISO:")).strip()
    texto, avisos = textos.revisar(texto, encerramento=comando != "humanizada")
    return {"texto": texto, "avisos": avisos_ia + avisos, "modelo": r.get("model"),
            "tipo": "mensagem" if comando == "humanizada" else "encerramento"}

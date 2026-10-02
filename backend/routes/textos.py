from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import llm, redator, teams, textos

router = APIRouter(prefix="/textos", tags=["textos"])


class RedigirIn(BaseModel):
    incident_number: str
    rascunho: str = ""
    comando: str | None = None
    texto_atual: str | None = None


@router.get("/comandos")
def comandos():
    return {"comandos": list(redator.COMANDOS), "llm": llm.available(), "manual": bool(redator.manual())}


@router.post("/revisar")
def revisar(body: dict):
    """Revisão de estilo do manual (só devolve; não grava)."""
    t, avisos = textos.revisar(body.get("texto") or "", body.get("encerramento", True))
    return {"texto": t, "avisos": avisos}


@router.post("/redigir")
def redigir(body: RedigirIn):
    """Texto no padrão do manual a partir do rascunho (IA via 9router). Só redige: nada vai ao ServiceNow."""
    from backend.payload import camera_codes, display_title
    from backend.routes.incidents import _get_inc, _ritm_do_incidente, close_draft_for
    from backend import scom
    if not llm.available():
        raise HTTPException(status_code=409, detail="IA desligada: confira o 9router em Configurações")
    if not body.rascunho.strip() and not body.comando:
        raise HTTPException(status_code=422, detail="Escreva o rascunho (o que foi feito) ou escolha um comando")
    inc = _get_inc(body.incident_number)
    draft = close_draft_for(inc)
    ritm = _ritm_do_incidente(inc["incident_number"])
    dados = {"incident_number": inc["incident_number"],
             "titulo": display_title(inc).get("titulo_padrao") or inc.get("short_description"),
             "localidade": inc.get("localidade"),
             "cameras": ", ".join(camera_codes(inc.get("camera_codigo"), inc.get("short_description") or "",
                                               inc.get("description") or "")),
             "host": scom.extract_host(inc.get("short_description") or "", inc.get("description") or ""),
             "ritm": ritm[0] if ritm else None, "cenario": draft["cenario"], "modelo": draft["texto"],
             "solicitante": teams.primeiro_nome(inc["caller_id"]) if inc.get("caller_id") else None,
             "saudacao": teams.saudacao(),
             "descricao": display_title(inc).get("descricao_util") or inc.get("description")}
    try:
        return redator.redigir(dados, body.rascunho, body.comando, body.texto_atual)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except llm.LLMError as e:
        raise HTTPException(status_code=502, detail=f"IA não respondeu: {e}")

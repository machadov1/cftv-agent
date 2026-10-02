from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from backend import agent, db

router = APIRouter(prefix="/agent", tags=["agent"])
MAX_IMG = 6
MAX_IMG_BYTES = 6_000_000  # por imagem, em data URL


class Msg(BaseModel):
    role: str
    content: str = ""

    @field_validator("role")
    @classmethod
    def ok_role(cls, v):
        if v not in ("user", "assistant"):
            raise ValueError("role deve ser user ou assistant")
        return v


class ChatIn(BaseModel):
    messages: list[Msg]
    images: list[str] = []  # data URLs do último pedido


@router.post("/chat")
def chat(body: ChatIn):
    if not body.messages or body.messages[-1].role != "user":
        raise HTTPException(status_code=422, detail="A última mensagem deve ser do usuário")
    if len(body.images) > MAX_IMG:
        raise HTTPException(status_code=422, detail=f"No máximo {MAX_IMG} imagens por pedido")
    for u in body.images:
        if not u.startswith("data:image/") or len(u) > MAX_IMG_BYTES:
            raise HTTPException(status_code=422, detail="Imagem inválida ou grande demais (máx. ~4 MB)")
    res = agent.run([m.model_dump() for m in body.messages[-12:]], body.images)
    ultimo = body.messages[-1].content[:120]
    db.add_history("AGENTE", "agente", f"{ultimo} | ações={len(res['actions'])} | {res.get('provider') or '-'}", True, res.get("ms", 0))
    return res

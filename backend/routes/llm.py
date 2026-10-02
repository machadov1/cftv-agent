from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import llm

router = APIRouter(prefix="/llm", tags=["llm"])

EDITAVEIS = {"nome", "base_url", "api_key_env", "model", "vision_model", "fallback_models", "enabled", "timeout"}


class ProviderIn(BaseModel):
    id: str
    nome: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    model: str | None = None
    vision_model: str | None = None
    fallback_models: list[str] | None = None
    enabled: bool | None = None
    timeout: int | None = None


class ConfigIn(BaseModel):
    providers: list[ProviderIn]  # na ordem de fallback


@router.get("/config")
def get_config():
    return llm.public_config()


@router.put("/config")
def put_config(body: ConfigIn):
    """Salva ordem, habilitação e modelos. Chaves continuam no .env."""
    atual = {p["id"]: p for p in llm.load()["providers"]}
    novo = []
    for p in body.providers:
        base = atual.get(p.id, {"id": p.id, "enabled": False, "timeout": 60})
        upd = {k: v for k, v in p.model_dump().items() if k in EDITAVEIS and v is not None}
        merged = {**base, **upd}
        if not merged.get("base_url") or not merged.get("model"):
            raise HTTPException(status_code=422, detail=f"{p.id}: base_url e model são obrigatórios")
        novo.append(merged)
    cfg = llm.load()
    cfg["providers"] = novo
    llm.save(cfg)
    return llm.public_config()


@router.post("/test/{pid}")
def test(pid: str, vision: bool = True):
    try:
        return llm.test_provider(pid, vision=vision)
    except llm.LLMError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/models/{pid}")
def models(pid: str):
    try:
        return llm.list_models(pid)
    except llm.LLMError as e:
        raise HTTPException(status_code=502, detail=f"Não consegui listar os modelos: {e}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Não consegui listar os modelos: {e.__class__.__name__}")

"""Camada de LLM: provedores OpenAI-compatíveis (9router, OpenRouter, ...) com fallback na ordem de data/llm.json.

Chaves ficam no .env (variável indicada em `api_key_env`); nunca são devolvidas pela API.
"""
import json
import os
import threading
import time

import requests

from backend.config import ROOT, config

PATH = ROOT / "data" / "llm.json"
_lock = threading.Lock()
_status: dict[str, dict] = {}  # por provedor: último ok/erro, latência


class LLMError(Exception):
    pass


def load() -> dict:
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


def save(cfg: dict) -> None:
    with _lock:
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)


def _key(p: dict) -> str | None:
    return os.getenv(p.get("api_key_env") or "") or None


def providers(enabled_only: bool = True) -> list[dict]:
    ps = load()["providers"]
    return [p for p in ps if p.get("enabled")] if enabled_only else ps


def available() -> bool:
    if config.SERVICENOW_MOCK:
        return False
    return any(_key(p) or "localhost" in p.get("base_url", "") for p in providers())


def public_config() -> dict:
    """Config sem segredos, com o estado de cada provedor."""
    out = []
    for p in providers(enabled_only=False):
        k = _key(p)
        out.append({**p, "key_present": bool(k), "key_hint": f"…{k[-4:]}" if k else None,
                    "status": _status.get(p["id"])})
    return {"providers": out}


def _parse(text: str) -> dict:
    """Tolera respostas SSE/whitespace (alguns gateways devolvem 'data: {...}' ou espaço antes do JSON)."""
    t = text.strip()
    if t.startswith("data:"):
        t = t[5:].strip()
    return json.JSONDecoder().raw_decode(t)[0]


def call(p: dict, messages: list, *, tools: list | None = None, max_tokens: int = 800,
         model: str | None = None) -> dict:
    """Uma chamada a um provedor específico. Devolve a mensagem do assistente + metadados."""
    headers = {"Content-Type": "application/json"}
    if _key(p):
        headers["Authorization"] = f"Bearer {_key(p)}"
    body = {"model": model or p["model"], "messages": messages, "max_tokens": max_tokens, "stream": False}
    if tools:
        body["tools"] = tools
    t0 = time.perf_counter()
    try:
        r = requests.post(f"{p['base_url'].rstrip('/')}/chat/completions", headers=headers, json=body,
                          timeout=p.get("timeout", 60))
        dt = round((time.perf_counter() - t0) * 1000)
        if not r.ok:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
        j = _parse(r.text)
        if "error" in j:
            raise LLMError(str(j["error"])[:200])
        msg = j["choices"][0]["message"]
    except requests.RequestException as e:
        _status[p["id"]] = {"ok": False, "erro": f"sem conexão: {e.__class__.__name__}", "at": time.time()}
        raise LLMError(f"{p['id']}: sem conexão ({e.__class__.__name__})") from e
    except LLMError as e:
        _status[p["id"]] = {"ok": False, "erro": str(e), "at": time.time()}
        raise LLMError(f"{p['id']}: {e}") from e
    except (ValueError, KeyError, IndexError) as e:
        _status[p["id"]] = {"ok": False, "erro": "resposta em formato inesperado", "at": time.time()}
        raise LLMError(f"{p['id']}: resposta em formato inesperado") from e
    _status[p["id"]] = {"ok": True, "ms": dt, "at": time.time(), "modelo_real": j.get("model")}
    return {"message": msg, "provider": p["id"], "model": j.get("model") or body["model"], "ms": dt,
            "usage": j.get("usage")}


def has_images(messages: list) -> bool:
    return any(isinstance(m.get("content"), list) and any(c.get("type") == "image_url" for c in m["content"])
               for m in messages)


def chat(messages: list, *, tools: list | None = None, max_tokens: int = 800) -> dict:
    """Tenta cada provedor habilitado, na ordem. Com imagem, usa o vision_model do provedor."""
    if config.SERVICENOW_MOCK:
        raise LLMError("LLM desligado em modo mock")
    img = has_images(messages)
    erros = []
    for p in providers():
        if not _key(p) and "localhost" not in p.get("base_url", ""):
            continue
        principal = (p.get("vision_model") or p["model"]) if img else p["model"]
        for model in [principal] + [m for m in p.get("fallback_models", []) if m != principal]:
            try:
                return call(p, messages, tools=tools, max_tokens=max_tokens, model=model)
            except LLMError as e:
                erros.append(f"{e} [{model}]")
    raise LLMError("Nenhum provedor respondeu. " + " | ".join(erros) if erros else "Nenhum provedor de LLM configurado")


def complete(prompt: str, max_tokens: int = 400) -> str:
    msg = chat([{"role": "user", "content": prompt}], max_tokens=max_tokens)["message"]
    return (msg.get("content") or "").strip()


# ---------- diagnóstico (tela de configuração) ----------
_PNG_TEST = None


def _test_image() -> str:
    """PNG 1x? com o texto 'CFTV 42' desenhado em pixels (sem depender de libs de imagem)."""
    global _PNG_TEST
    if _PNG_TEST:
        return _PNG_TEST
    import base64
    import struct
    import zlib
    glyphs = {  # 5x7
        "4": ["10010", "10010", "10010", "11111", "00010", "00010", "00010"],
        "2": ["01110", "10001", "00001", "00110", "01000", "10000", "11111"],
    }
    scale, text = 8, "42"
    w, h = (len(text) * 6 + 1) * scale, 9 * scale
    rows = []
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            gx, gy = x // scale, y // scale - 1
            ch, cx = divmod(gx, 6)
            on = 0 <= gy < 7 and ch < len(text) and cx < 5 and glyphs[text[ch]][gy][cx] == "1"
            row += bytes([0, 0, 0] if on else [255, 255, 255])
        rows.append(bytes(row))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")
    _PNG_TEST = "data:image/png;base64," + base64.b64encode(png).decode()
    return _PNG_TEST


def test_provider(pid: str, *, vision: bool = True) -> dict:
    p = next((x for x in providers(enabled_only=False) if x["id"] == pid), None)
    if not p:
        raise LLMError("Provedor não encontrado")
    out = {"provider": pid, "texto": None, "ferramentas": None, "visao": None}

    def run(name, fn):
        t0 = time.perf_counter()
        try:
            out[name] = {"ok": True, **fn(), "ms": round((time.perf_counter() - t0) * 1000)}
        except Exception as e:  # noqa: BLE001
            out[name] = {"ok": False, "erro": str(e)[:240], "ms": round((time.perf_counter() - t0) * 1000)}

    def texto():
        r = call(p, [{"role": "user", "content": "Responda apenas com a palavra: pronto"}], max_tokens=300)
        c = (r["message"].get("content") or "").strip()
        return {"resposta": c[:80], "modelo": r["model"], "passou": "pronto" in c.lower()}

    def ferramentas():
        tools = [{"type": "function", "function": {"name": "buscar_incidente", "description": "Busca um incidente",
                  "parameters": {"type": "object", "properties": {"numero": {"type": "string"}}, "required": ["numero"]}}}]
        r = call(p, [{"role": "user", "content": "Use a ferramenta para buscar o incidente INC0000042."}], tools=tools, max_tokens=400)
        tc = r["message"].get("tool_calls") or []
        args = tc[0]["function"]["arguments"] if tc else ""
        return {"modelo": r["model"], "passou": bool(tc) and "INC0000042" in args, "chamada": args[:80]}

    def visao():
        msgs = [{"role": "user", "content": [
            {"type": "text", "text": "Qual número aparece na imagem? Responda só o número."},
            {"type": "image_url", "image_url": {"url": _test_image()}}]}]
        r = call(p, msgs, max_tokens=300, model=p.get("vision_model") or p["model"])
        c = (r["message"].get("content") or "").strip()
        return {"resposta": c[:80], "modelo": r["model"], "passou": "42" in c}

    run("texto", texto)
    run("ferramentas", ferramentas)
    if vision:
        run("visao", visao)
    return out


def list_models(pid: str) -> list[dict]:
    p = next((x for x in providers(enabled_only=False) if x["id"] == pid), None)
    if not p:
        raise LLMError("Provedor não encontrado")
    headers = {"Authorization": f"Bearer {_key(p)}"} if _key(p) else {}
    r = requests.get(f"{p['base_url'].rstrip('/')}/models", headers=headers, timeout=20)
    if not r.ok:
        raise LLMError(f"HTTP {r.status_code}")
    out = []
    for m in _parse(r.text).get("data", []):
        c = m.get("capabilities") or {}
        arch = (m.get("architecture") or {}).get("input_modalities") or []
        out.append({"id": m["id"], "vision": bool(c.get("vision") or "image" in arch),
                    "tools": c.get("tools"), "contexto": c.get("contextWindow") or m.get("context_length")})
    return sorted(out, key=lambda m: (not m["vision"], m["id"]))

"""Cliente somente leitura da HTTP API do Digifort (docs em API-DIGIFORT/): localizar câmera, ver se voltou, tirar snapshot.

A câmera é identificada pelo nome cadastrado no servidor; o código do incidente ("Número do Objeto") é usado como máscara.
Credenciais vêm do .env (conta de serviço), nunca da planilha de servidores.
"""
import io
import json
import re
import threading
import unicodedata
from datetime import datetime

import requests

from backend.config import config, ROOT

CACHE_PATH = ROOT / "data" / "digifort_cache.json"  # código -> servidor/nome já localizados (evita varrer a unidade toda vez)
_lock = threading.Lock()

_log: list[str] = []
_log_lock = threading.Lock()


class DigifortError(Exception):
    pass


CRED_PATH = ROOT / "data" / "digifort_credenciais.json"  # opcional, fora do git: {"10.58.8.27": {"usuario": "", "senha": ""}}


def debug_log(msg: str) -> None:
    """Registra uma linha de debug."""
    with _log_lock:
        _log.append(msg)


def get_debug_log() -> list[str]:
    """Retorna o log acumulado."""
    with _log_lock:
        return list(_log)


def clear_debug_log() -> None:
    """Limpa o log."""
    with _log_lock:
        _log.clear()


def configured() -> bool:
    return bool(config.DIGIFORT_USER and config.DIGIFORT_PASSWORD)


def _cred(ip: str) -> tuple[str, str]:
    """Credencial do servidor: a específica do arquivo (por IP), senão a conta padrão do .env."""
    try:
        c = json.loads(CRED_PATH.read_text(encoding="utf-8")).get(ip) or {}
    except (OSError, ValueError):
        c = {}
    return c.get("usuario") or config.DIGIFORT_USER, c.get("senha") or config.DIGIFORT_PASSWORD


def _get(ip: str, path: str, params: dict | None = None) -> requests.Response:
    if not configured():
        raise DigifortError("Digifort não configurado: defina DIGIFORT_USER e DIGIFORT_PASSWORD no .env")
    user, pwd = _cred(ip)
    url = f"http://{ip}:{config.DIGIFORT_PORT}/Interface/{path}"
    debug_log(f"→ {ip}:{config.DIGIFORT_PORT}/Interface/{path}")
    try:
        r = requests.get(url, params=params or {}, auth=(user, pwd), timeout=(3, config.DIGIFORT_TIMEOUT))
        debug_log(f"← {r.status_code} ({len(r.content)} bytes)")
        return r
    except requests.exceptions.Timeout:
        msg = f"{ip}: timeout ({config.DIGIFORT_TIMEOUT}s); porta {config.DIGIFORT_PORT} aberta?"
        debug_log(f"✗ {msg}")
        raise DigifortError(msg) from None
    except requests.exceptions.ConnectionError as e:
        msg = f"{ip}: sem conexão; VPN/rede/porta {config.DIGIFORT_PORT}?"
        debug_log(f"✗ {msg}")
        raise DigifortError(msg) from e
    except requests.RequestException as e:
        msg = f"{ip}: erro ({type(e).__name__})"
        debug_log(f"✗ {msg}")
        raise DigifortError(msg) from e


_KV = re.compile(r"^\s*([A-Za-z0-9_.]+)\s*[=:]\s*(.*?)\s*$")


def parse_text(body: str) -> dict:
    """Resposta em texto (CHAVE=valor por linha), chaves em maiúsculas."""
    out = {}
    for line in (body or "").splitlines():
        m = _KV.match(line)
        if m:
            out[m.group(1).upper()] = m.group(2)
    return out


def _check(resp: requests.Response, ip: str) -> dict:
    if resp.status_code in (401, 403):
        msg = f"usuário/senha recusados pelo Digifort ({resp.status_code})"
        debug_log(f"✗ {ip}: {msg}")
        raise DigifortError(f"{ip}: {msg}")
    kv = parse_text(resp.text)
    code = kv.get("RESPONSE_CODE") or kv.get("RESPONSE.CODE")
    if code and code not in ("0", "200"):
        msg = f"código {code} {kv.get('RESPONSE_MESSAGE', '')}".strip()
        debug_log(f"✗ {ip}: {msg}")
        raise DigifortError(f"{ip}: Digifort respondeu {msg}")
    return kv


def version(ip: str) -> dict:
    """Teste de conexão: versão da API (e confere a credencial)."""
    debug_log(f"Testando {ip}...")
    user, _ = _cred(ip)
    debug_log(f"Credencial: {user}@{ip}")
    resp = _get(ip, "GetAPIVersion", {"ResponseFormat": "Text"})
    kv = _check(resp, ip)
    debug_log(f"✓ {ip} respondeu: Digifort {kv.get('VERSION')} / API {kv.get('APIVERSION')}")
    return {"ip": ip, "http": resp.status_code, "campos": kv, "bruto": resp.text[:300]}


def list_cameras(ip: str, mask: str) -> list[str]:
    """Nomes das câmeras do servidor que casam com a máscara (sem diferenciar maiúsculas; aceita * e ?)."""
    debug_log(f"Procurando '{mask}' em {ip}...")
    resp = _get(ip, "Cameras/GetCameras", {"Cameras": mask, "Fields": "Name", "ResponseFormat": "Text"})
    kv = _check(resp, ip)
    cams = [v for k, v in sorted(kv.items()) if re.fullmatch(r"CAMERA_\d+_NAME", k) and v]
    if cams:
        debug_log(f"Encontradas {len(cams)}: {', '.join(cams[:3])}" + ("..." if len(cams) > 3 else ""))
    else:
        debug_log(f"Nenhuma câmera encontrada com '{mask}'")
    return cams


def camera_state(ip: str, name: str) -> dict:
    """{'working': bool|None, 'active': bool|None, 'inactive_s': int|None}: há quanto tempo a câmera está sem sinal."""
    debug_log(f"Status de '{name}' em {ip}...")
    resp = _get(ip, "Cameras/GetStatus", {"Cameras": name, "Fields": "Active,Working,ActiveTime,InactiveTime",
                                           "ResponseFormat": "Text"})
    kv = _check(resp, ip)

    def pick(field):
        for k, v in kv.items():
            if re.fullmatch(rf"CAMERA_\d+_{field}", k):
                return v
        return None

    def boo(v):
        return None if v is None else v.strip().lower() in ("true", "1", "yes")

    def num(v):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None

    return {"active": boo(pick("ACTIVE")), "working": boo(pick("WORKING")),
            "inactive_s": num(pick("INACTIVETIME")), "active_s": num(pick("ACTIVETIME"))}


def _motivo(body: str) -> str:
    """Motivo do erro, que o Digifort devolve em XML (<Code>/<Message>) ou em texto (RESPONSE_*)."""
    m = re.search(r"<Code>(\d+)</Code>\s*<Message>(.*?)</Message>", body or "", re.S)
    if m:
        return f"{m.group(1)} {m.group(2).strip()}"
    kv = parse_text((body or "")[:600])
    return f"{kv.get('RESPONSE_CODE', '?')} {kv.get('RESPONSE_MESSAGE', '')}".strip()


def server_time(ip: str) -> str | None:
    """Data/hora do servidor Digifort ('dd/mm/aaaa hh:mm:ss'); o relógio interno da câmera pode estar errado."""
    try:
        kv = _check(_get(ip, "Server/GetInfo", {"ResponseFormat": "Text"}), ip)
    except DigifortError:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}:\d{2}:\d{2})", kv.get("DATETIME", ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)} {m.group(4)}" if m else None


def _com_faixa(jpeg: bytes, texto: str) -> bytes:
    """Acrescenta uma faixa abaixo da imagem com o texto (sem cobrir o vídeo). A data gravada pela câmera fica como está."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    h = max(34, img.height // 18)
    out = Image.new("RGB", (img.width, img.height + h), (0, 0, 0))
    out.paste(img, (0, 0))
    font = None
    for f in ("consola.ttf", "arial.ttf"):
        try:
            font = ImageFont.truetype(f, int(h * 0.62))
            break
        except OSError:
            continue
    font = font or ImageFont.load_default()
    d = ImageDraw.Draw(out)
    box = d.textbbox((0, 0), texto, font=font)
    d.text((14, img.height + (h - (box[3] - box[1])) // 2 - box[1]), texto, fill=(255, 255, 255), font=font)
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def snapshot(ip: str, name: str) -> bytes:
    """JPEG ao vivo com faixa inferior: nome da câmera e hora do servidor Digifort (ou desta máquina, se ele não informar).
    A marca d'água nativa não é usada: servidores 7.3 (API 1.9.1) a ignoram, e o relógio da câmera pode estar errado."""
    debug_log(f"Capturando snapshot de '{name}' em {ip}...")
    try:
        resp = _get(ip, "Cameras/GetSnapshot", {"Camera": name, "Profile": "Recording", "Width": 1280, "Height": 720,
                                                 "KeepAspectRatio": "TRUE", "Quality": 85, "RenderInfo": "Name"})
    except DigifortError as e:
        debug_log(f"✗ Falha ao capturar snapshot: {e}")
        raise
    if resp.status_code in (401, 403):
        raise DigifortError(f"{ip}: usuário/senha recusados pelo Digifort ({resp.status_code})")
    if "image" not in (resp.headers.get("Content-Type") or "").lower() or len(resp.content) < 500:
        raise DigifortError(f"{ip}: sem imagem ({_motivo(resp.text)})")
    hora = server_time(ip)
    origem = "hora do servidor Digifort" if hora else "hora desta máquina"
    hora = hora or datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    return _com_faixa(resp.content, f"{name}   |   {hora}   |   {origem}")


# ---------- localização da câmera ----------
def _fold(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower())


def _cache() -> dict:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _remember(code: str, server: dict) -> None:
    with _lock:
        c = _cache()
        c[_fold(code)] = server
        try:
            CACHE_PATH.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass


def locate(code: str, servers: list[dict]) -> dict:
    """Acha a câmera nos servidores da unidade: nome exato > máscara `código*` > `*código*` (só se for candidata única).

    Devolve {'achada': {'servidor','ip','nome'}|None, 'candidatas': [...], 'erros': [...], 'tentados': [...]}.
    """
    res = {"achada": None, "candidatas": [], "erros": [], "tentados": []}
    known = _cache().get(_fold(code))
    order = list(servers)
    if known:  # o servidor onde já a encontramos vai na frente
        order.sort(key=lambda s: s["ip"] != known.get("ip"))
    for s in order:
        res["tentados"].append(s["nome"])
        try:
            for mask in (code, f"{code}*", f"*{code}*"):
                nomes = list_cameras(s["ip"], mask)
                if nomes:
                    break
        except DigifortError as e:
            res["erros"].append(str(e))
            continue
        for n in nomes:
            cand = {"servidor": s["nome"], "ip": s["ip"], "nome": n}
            if _fold(n) == _fold(code):
                _remember(code, cand)
                res["achada"] = cand
                return res
            res["candidatas"].append(cand)
    if len(res["candidatas"]) == 1:
        res["achada"] = res["candidatas"][0]
        _remember(code, res["achada"])
    return res

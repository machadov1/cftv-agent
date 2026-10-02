"""Alerta SCOM (skill operador-cftv, seção 5.1): valida por ping na máquina local e gera evidência."""
import os
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.config import ROOT

DOMAIN = ".Americas.mittalco.com"
EVIDENCE_DIR = ROOT / "data" / "evidencias"
_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,62}$")
_IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_FROM_TEXT = re.compile(r"on computer\s+([A-Za-z0-9-]+)", re.IGNORECASE)

# Work note: validação por ping (10 pacotes, sem perdas = comunicação SCOM normalizada)
WORK_NOTE = (
    "Causa base: Alerta automático de falha de heartbeat do Microsoft Monitoring Agent (SCOM) no servidor {host}.\n"
    "\n"
    "Validação executada: Ping de 10 pacotes ao servidor respondendo sem perdas (0%).\n"
    "Resultado: Servidor está online e acessível na rede. Comunicação com o monitoramento normalizada.\n"
    "\n"
    "Evidência anexada ao incidente. Incidente encerrado sem necessidade de intervenção operacional."
)

def is_scom_alert(short_description: str, description: str = "") -> bool:
    t = f"{short_description} {description}".lower()
    return "failed to heartbeat" in t or "comunicando com scom" in t or "comunicando com o scom" in t


# Alertas automáticos em geral (TrueSight/SCOM/BMC): heartbeat, uso de banda, disco... Abertos pelo usuário de monitoramento.
_AUTO_TEXT = re.compile(r"failed to heartbeat|comunicando com (o )?scom|over threshold|network adapter|bandwidth",
                        re.IGNORECASE)


def is_auto_alert(short_description: str, description: str = "", caller: str = "") -> bool:
    """Alerta de monitoramento (não é chamado de usuário): título e categoria ficam como vieram."""
    return (is_scom_alert(short_description, description) or "MONITORING" in (caller or "").upper()
            or bool(_AUTO_TEXT.search(f"{short_description} {description}")))


_CI_HOST = re.compile(r"^(?:LCB\s*-\s*)?([A-Za-z]{2,4}-[A-Za-z0-9-]{2,40})$")


def host_do_ci(ci_nome: str | None) -> str | None:
    """'LCB - PRJ-APP-CFTV02' -> 'PRJ-APP-CFTV02' (nome do IC afetado, quando é um servidor)."""
    m = _CI_HOST.match((ci_nome or "").strip())
    return m.group(1).upper() if m else None


def extract_host(short_description: str, description: str = "") -> str | None:
    for text in (short_description, description):
        m = _FROM_TEXT.search(text or "")
        if m:
            return m.group(1).upper()
    return None


# Prefixo do hostname -> unidade (quando o servidor não está na lista "Gestão de Servidores")
HOST_PREFIXO = {
    "RES": "Resende", "RSD": "Resende", "IRA": "Iracemápolis", "BMA": "Barra Mansa", "BM": "Barra Mansa",
    "BBD": "Bauru", "PIR": "Piracicaba", "MDE": "João Monlevade", "JDF": "Juiz de Fora", "SAB": "Sabará",
    "GUA": "Guarulhos", "JAB": "Jaboatão", "CAN": "Candeias", "RDP": "Rio das Pedras", "TUB": "Tubarão",
    "PRJ": "Projects (monitoramento)",
}


def unidade_do_host(host: str | None) -> str | None:
    """Unidade do servidor do alerta: lista de servidores (coluna Unidade), senão o prefixo do nome (RES-APP-CFTV04)."""
    if not host:
        return None
    from backend import servidores
    ficha = servidores.find(host)
    if ficha and ficha.get("unidade") and ficha["unidade"] != "Projects":
        return ficha["unidade"]
    # servidor de Projects (PRJ-APP-CFTV02, mesmo fisicamente numa usina) vai para a fila de Projects
    loc = HOST_PREFIXO.get(host.split("-")[0].upper())
    if not loc and ficha and ficha.get("unidade") == "Projects":
        return "Projects (monitoramento)"
    return loc


def run_ping(host: str, domain: str = DOMAIN, count: int = 10, target: str | None = None) -> dict:
    if not _HOST_RE.match(host):
        raise ValueError("Host inválido")
    if target is not None and not _IP_RE.match(target):
        raise ValueError("Destino inválido")
    target = target or f"{host}{domain}"
    proc = subprocess.run(["ping", "-n", str(count), target], capture_output=True, timeout=60)
    out = proc.stdout.decode("cp850", errors="replace")
    loss = re.search(r"\((\d+)%", out)
    ip = re.search(r"\[?(\d{1,3}(?:\.\d{1,3}){3})\]?", out)
    perda = int(loss.group(1)) if loss else None
    return {
        "host": host, "target": target, "ip": ip.group(1) if ip else None,
        "perda_percentual": perda,
        "ok": proc.returncode == 0 and perda == 0,
        "resolveu": bool(ip),
        "saida": out.strip(),
    }


BRT = timezone(timedelta(hours=-3))  # Brasília (sem horário de verão)
VALIDADE_MIN = 30  # validação mais velha que isso não vale para a work note


def evidence_path(host: str, incident: str | None = None) -> Path:
    nome = f"ping_{incident.upper()}_{host.upper()}.png" if incident else f"ping_{host.upper()}.png"
    return EVIDENCE_DIR / nome


def render_evidence(host: str, ping: dict, incident: str | None = None) -> Path:
    """PNG desenhado a partir da saída REAL do ping que acabou de rodar (sem abrir janela na tela)."""
    from PIL import Image, ImageDraw, ImageFont
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    try:
        font, bold = ImageFont.truetype(str(fonts / "consola.ttf"), 16), ImageFont.truetype(str(fonts / "consolab.ttf"), 16)
    except OSError:
        font = bold = ImageFont.load_default()
    quando = datetime.now(BRT).strftime("%d/%m/%Y %H:%M:%S")
    perda = ping.get("perda_percentual")
    head = [f"Teste de conectividade - {host}  ({ping.get('ip') or 'sem IP'})",
            f"Executado na estação {os.environ.get('COMPUTERNAME', '?')} em {quando} (Brasília)"]
    corpo = [f"C:\\> ping -n 10 {ping.get('target') or host}", ""] + (ping.get("saida") or "").splitlines()
    pe = f"Resultado: {perda if perda is not None else '?'}% de perda"
    lh, pad = 21, 18
    w = max(760, max(int(font.getlength(t)) for t in head + corpo + [pe]) + 2 * pad)
    h = pad * 2 + lh * (len(head) + len(corpo) + 3)
    img = Image.new("RGB", (w, h), (12, 12, 12))
    d = ImageDraw.Draw(img)
    y = pad
    for t in head:
        d.text((pad, y), t, font=bold, fill=(235, 235, 235)); y += lh
    d.line((pad, y + 6, w - pad, y + 6), fill=(90, 90, 90), width=1); y += lh
    for t in corpo:
        d.text((pad, y), t, font=font, fill=(204, 204, 204)); y += lh
    d.text((pad, y + 6), pe, font=bold, fill=(80, 200, 120) if ping.get("ok") else (230, 90, 80))
    out = evidence_path(host, incident)
    img.save(out, "PNG")
    return out


def ultima_validacao(incident: str, agora: datetime | None = None) -> dict | None:
    """Último ping OK do incidente (histórico) com até VALIDADE_MIN minutos e a imagem ainda no disco. Senão None."""
    from backend import db
    for h in db.list_history(20, incident.upper(), "ping"):
        campos = dict(kv.split("=", 1) for kv in (h.get("resultado") or "").split() if "=" in kv)
        if campos.get("ok") != "True" or not campos.get("evid"):
            return None  # o último teste é o que vale: se falhou, não há validação
        quando = datetime.strptime(str(h["created_at"])[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if (agora or datetime.now(timezone.utc)) - quando > timedelta(minutes=VALIDADE_MIN):
            return None
        arq = EVIDENCE_DIR / Path(campos["evid"]).name
        if not arq.exists():
            return None
        return {"host": campos.get("host"), "perda": campos.get("perda"), "arquivo": arq,
                "hora": quando.astimezone(BRT).strftime("%H:%M")}
    return None


def ping_host(host: str, *, ip: str | None = None, domain: str = DOMAIN, evidence: bool = True,
              incident: str | None = None) -> dict:
    """Ping de qualquer servidor (FQDN; se o DNS falhar e houver IP da lista, tenta o IP). Sem texto de encerramento."""
    t0 = time.perf_counter()
    ping = run_ping(host, domain)
    if not ping["resolveu"] and ip and _IP_RE.match(ip):
        ping = run_ping(host, domain, target=ip)
    res = {"host": host, "ping": ping, "ok": ping["ok"], "evidencia": None, "work_note": None}
    if not ping["ok"]:
        res["aviso"] = ("Sem resposta/DNS não resolvido: verifique a VPN."
                        if not ping["resolveu"] else "Houve perda de pacotes: não tratar como resolvido; reportar ao Victor.")
        return res
    if evidence:
        res["evidencia"] = render_evidence(host, ping, incident).name
    res["tempo_s"] = round(time.perf_counter() - t0, 1)
    return res


def check(short_description: str, description: str = "", *, domain: str = DOMAIN, evidence: bool = True,
          incident: str | None = None) -> dict:
    """Fluxo 5.1: host → ping → (se 0% de perda) print + work note. Com perda: só reporta."""
    host = extract_host(short_description, description)
    if not host:
        return {"ok": False, "erro": "Host não encontrado no texto do alerta."}
    res = ping_host(host, domain=domain, evidence=evidence, incident=incident)
    res["ressalva"] = ("Ping OK prova que o servidor está na rede, não que o Health Service voltou a enviar heartbeat "
                       "(confirmação forte: console do SCOM ou saída na porta 5723).")
    if res["ok"]:
        res["work_note"] = WORK_NOTE.format(host=host)
    else:
        res["aviso"] += " Nada de texto de encerramento."
    return res

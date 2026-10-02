"""Monta o PATCH da primeira tratativa (skill operador-cftv, seção 5)."""
import json
import re
from functools import lru_cache

from backend.config import ROOT
from backend import scom, a4, textos
from backend.scom import is_auto_alert

WORK_NOTE = "Encaminhado para equipe."
# skill, fluxo 8: acesso vai por requisição. No despacho só o fato; o contato com o solicitante entra no encerramento.
WORK_NOTE_ACESSO = textos.acesso_despacho()
ASSIGNED_TO = "a37f083f3b5c7a548c9f67dc73e45a50"
BUSINESS_SERVICE = "26d75cb8dba5bf00f80f9972ca961978"
TYPE_DEFAULT = "00020f981bbb56d0febdeac82d4bcbff"
TYPE_LORA = "7bec9dfedb913700e5f36451ca9619c6"

# BM-LAM-CLI-049 / BM-PAT-G-052 (vários segmentos) antes de RES027 / MDE-012 / 03SUC, para não cortar o código ao meio
_CODE = re.compile(r"(?<![A-Za-z0-9-])(?:[A-Z]{2,4}(?:-[A-Z][A-Z0-9]{0,4}){1,3}-\d{2,4}[A-Z]?|[A-Z]{2,4}-?\d{2,4}[A-Z]?"
                   r"|\d{2}[A-Z]{2,4})(?![A-Za-z0-9])")


@lru_cache(maxsize=1)
def _mapa() -> dict:
    with open(ROOT / "data" / "mapeamentos.json", encoding="utf-8") as f:
        return json.load(f)


def mapa_localidade(localidade: str | None) -> dict:
    return _mapa().get(localidade or "", {})


def _codes(text: str) -> list[str]:
    seen = []
    for m in _CODE.findall(text or ""):
        m = m.upper()
        if m not in seen:
            seen.append(m)
    return seen


_TAG_PREFIX = re.compile(r"^\s*(?:\[[^\]]*\]\s*[-–]?\s*)+")
_DOWN = re.compile(r"tela preta|sem imagem|sem sinal|sem conex|sem comunica|problemas? (?:de|na|com) conex|falha (?:de|na) conex|offline|off-line|fora de acesso|fora do ar|reconectar|instabilidade", re.I)
_HOST = re.compile(r"\b[A-Z]{2,4}-[A-Z]{2,4}-[A-Z]{3,5}\d{0,3}\b")


_ACESSO = re.compile(r"(?:acesso|acessar)\s+(?:[àa]s?\s+|ao\s+|aos\s+)?(?:c[âa]meras?|imagens|cftv|digifort|grava[çc][õo]es)"
                     r"|(?:liberar|libera[çc][ãa]o\s+de|solicita[çc][ãa]o\s+de|solicito|pedido\s+de)\s+acesso", re.I)


def is_access_request(short: str, description: str = "") -> bool:
    """Pedido de acesso às câmeras (não é falha): segue o fluxo 8 da skill."""
    t = f"{short or ''} {relevant_text(description)}"
    # "sem acesso às câmeras", "não consigo acessar as imagens" = falha, não pedido
    return any(not re.search(r"\b(?:sem|n[ãa]o|perd\w*|falha\w*|erro)\b[^.\n]{0,25}$", t[:m.start()], re.I)
               for m in _ACESSO.finditer(t))


def clean_short(short: str) -> str:
    """Tira prefixos de tag ([CFTV], [Outros Sistemas]...) e traços soltos do título original."""
    t = _TAG_PREFIX.sub("", short or "")
    t = re.sub(r"^\s*[-–]+\s*", "", t)
    t = re.sub(r"\s+[-–]\s+[-–]\s+", " - ", t)
    return t.strip(" -–\t")


def relevant_text(description: str) -> str:
    """Corpo útil da descrição: descarta o texto-padrão do formulário (linhas '** ... **', exemplos de IC)."""
    d = description or ""
    m = re.search(r"Descri[çc][ãa]o do problema:\s*(.+?)(?:\r?\n\s*\r?\n|Nome do solicitante|$)", d, re.I | re.S)
    body = m.group(1) if m else d
    return "\n".join(l for l in body.splitlines() if not l.strip().startswith("**"))


def extract_codes(short: str, description: str) -> list[str]:
    """Códigos de câmera: campos estruturados do formulário > título > corpo da descrição > números soltos."""
    d = description or ""
    campos = re.findall(r"(?:C[óo]digo do equipamento|Nome do ponto de imagem[^:\n]*)\s*:\s*([^\r\n]+)", d, re.I)
    cods = _codes(" ".join(campos))
    if cods:
        return cods
    # "Nome do ponto de imagem: 399, 407, 72 394": a numeração do mosaico, sem prefixo
    nums = [n for c in campos if re.fullmatch(r"(?:\d{1,4}|[\s,;/]+|\be\b)+", c.strip()) for n in field_codes(c)]
    cods = list(dict.fromkeys(nums)) or _codes(short) or _codes(relevant_text(d))
    if cods:
        return cods
    m = re.search(r"c[âa]meras?\s+((?:\d{1,3}\s*(?:,|/|\be\b)?\s*)+)", f"{short} {relevant_text(d)}", re.I)
    return list(dict.fromkeys(re.findall(r"\d{1,3}", m.group(1)))) if m else []


def field_codes(valor: str | None) -> list[str]:
    """Códigos do campo 'Número do Objeto' (um ou vários separados por , / e).
    "MDE 011, 001" herda o prefixo (MDE-011, MDE-001); frase ("Câmeras sem conexão RES027 RES028") vale pelos códigos citados."""
    v = (valor or "").strip()
    if re.fullmatch(r"(?:\d{1,4}|[\s,;/]+|\be\b)+", v):  # "209 e 177", "71, 72 394": numeração pura
        return list(dict.fromkeys(re.findall(r"\d{1,4}", v)))
    partes = [p for p in re.split(r"\s*(?:,|/|;|\be\b)\s*", v) if p]
    cods, prefixo = [], None
    for p in partes:
        m = re.fullmatch(r"([A-Za-z]{2,6})\s+(\d{1,4})", p)
        if m:
            prefixo = m.group(1).upper()
            cods.append(f"{prefixo}-{m.group(2)}")
        elif prefixo and re.fullmatch(r"\d{1,4}", p):
            cods.append(f"{prefixo}-{p}")
        elif re.fullmatch(r"[A-Za-z]{1,6}[\w.\-]*\d[\w.\-]*", p) or re.fullmatch(r"\d{1,4}-?[A-Za-z]{2,6}", p):  # 03-SUC
            cods.append(p.upper())
        elif " " in p:
            cods += _codes(p)
    return list(dict.fromkeys(cods))


def camera_codes(camera_codigo: str | None, short: str = "", description: str = "") -> list[str]:
    """Códigos de câmera do incidente: campo 'Número do Objeto' primeiro; vazio/texto livre, o que o texto cita (letras+número)."""
    return field_codes(camera_codigo) or [c for c in extract_codes(short, description) if field_codes(c)]


def build_title(cidade: str, short: str, description: str, lora: bool, camera_codigo: str | None = None) -> tuple[str, bool]:
    """Título no padrão da skill (seção 10): `[Cidade] - ...`. (título, padronizado?).
    Sem padrão reconhecido: mantém o original limpo, com a cidade na frente, e marca como não padronizado."""
    if re.match(rf"^\s*{re.escape(cidade)}\s*-", short, re.IGNORECASE):
        return short.strip(), True
    limpo = clean_short(short)
    corpo = relevant_text(description)
    low = f"{limpo} {corpo}".lower()
    if not lora and is_access_request(short, description):
        return f"{cidade} - Solicitação de acesso às câmeras", True

    if lora:
        tags = re.findall(r"(?<!\d)\d{3,4}(?!\d)", short) or re.findall(r"(?<!\d)\d{3,4}(?!\d)", corpo)
        tags = list(dict.fromkeys(tags))
        if tags:
            return f"{cidade} - TAG LORA {' / '.join(tags)} - Falha de funcionalidade", True
        return f"{cidade} - {limpo or short.strip()}", False

    # "[CFTV] - Imagem degradada" não diz "câmera": o código no campo (ou falar de imagem) já basta
    camera = (re.search(r"c[âa]mera|ptz|cúpula|cupula|imagem|tela preta", low) is not None
              or bool(field_codes(camera_codigo)))
    if re.search(r"servidor", limpo, re.I) and not re.search(r"c[âa]mera", limpo, re.I) and _DOWN.search(low):
        hosts = [h for h in dict.fromkeys(_HOST.findall(f"{short} {corpo}")) if "FAILOVER" not in h.upper()]
        if hosts:
            return f"{cidade} - Servidor {hosts[0]} sem conexão", True
        plural = "servidores" in limpo.lower()
        return f"{cidade} - {'Servidores' if plural else 'Servidor'} sem conexão", True

    if camera:
        cods = field_codes(camera_codigo) or extract_codes(short, description)
        if cods:
            um = len(cods) == 1
            cam = f"Câmera {cods[0]}" if um else f"Câmeras {'/'.join(cods)}"
        else:
            um = not re.search(r"c[âa]meras", low)
            cam = "Câmera" if um else "Câmeras"
        if "ptz" in low and um and cods:
            return f"{cidade} - {cam} sem movimentação PTZ", True
        if re.search(r"dano f[ií]sico|quebrad|danificad", low) and um and cods:
            return f"{cidade} - {cam} com dano físico", True
        if "cúpula suja" in low or "cupula suja" in low:
            return f"{cidade} - {cam} com cúpula suja", True
        if "degradad" in low:
            return f"{cidade} - {cam} com imagem degradada", True
        if _DOWN.search(low):
            return f"{cidade} - {cam} sem conexão", True
    return f"{cidade} - {limpo or short.strip()}", False


def display_title(inc: dict) -> dict:
    """Título padronizado para exibir na fila/painel (não altera o incidente). Detecta A4 na hora."""
    loc = inc.get("localidade")
    short = inc.get("short_description") or ""
    desc = inc.get("description") or ""
    cmdb = inc.get("cmdb_ci") or ""
    util = re.sub(r"\s+", " ", relevant_text(desc)).strip()
    acesso = is_access_request(short, desc)

    # Detectar A4 (calculado na hora, não gravado)
    a4_sistema, a4_fila, a4_grupo = None, None, None
    is_a4_bool = a4.is_a4(short, desc, cmdb)
    if is_a4_bool[0]:
        a4_sistema = is_a4_bool[1]
        a4_fila, a4_grupo = a4.fila_a4_para_unidade(loc) if loc else (None, None)

    if not loc:
        return {"titulo_padrao": None, "titulo_ok": False, "descricao_util": util, "acesso": acesso,
                "a4": a4_sistema, "a4_fila": a4_fila}
    m = mapa_localidade(loc)
    if m.get("alerta") or is_auto_alert(short, desc, inc.get("caller_id") or ""):  # alertas automáticos: manter o original
        return {"titulo_padrao": short, "titulo_ok": True, "descricao_util": util, "acesso": False,
                "a4": a4_sistema, "a4_fila": a4_fila}
    t, ok = build_title(m.get("cidade") or loc, short, desc, "LORA" in loc, inc.get("camera_codigo"))
    return {"titulo_padrao": t, "titulo_ok": ok, "descricao_util": util, "acesso": acesso,
            "a4": a4_sistema, "a4_fila": a4_fila}


def is_alert(localidade: str | None) -> bool:
    return bool(mapa_localidade(localidade).get("alerta"))


def severity_line(impact: str | None, urgency: str | None) -> str | None:
    parts = ([f"impacto alterado para {impact}"] if impact else []) + ([f"urgência alterada para {urgency}"] if urgency else [])
    if not parts:
        return None
    return ("Incidente em verificação, severidade alterada para sequência das tratativas e verificações "
            f"({', '.join(parts)}).")


def camera_line(cam: dict) -> str:
    codes = cam["codigos"]
    alvo = f"da câmera {codes[0]}" if len(codes) == 1 else f"das câmeras {' / '.join(codes)}"
    return (f"Realizada verificação {alvo} às {cam['hora']} no Digifort, operando normalmente no momento da checagem. "
            "Evidência anexada ao incidente.")


def build_first_touch(inc: dict, final: dict, current: dict | None,
                      contexto: dict | None = None) -> tuple[dict, list[str]]:
    """Retorna (campos do PATCH, avisos). `current` = estado atual no SN (state, work_notes).
    `contexto` = testes feitos antes do despacho: {"scom": scom.ultima_validacao(...), "camera": {codigos, hora}}."""
    contexto = contexto or {}
    warnings: list[str] = []
    loc = final.get("localidade")
    m = mapa_localidade(loc)
    short, desc = inc.get("short_description") or "", inc.get("description") or ""
    # alerta automático (TrueSight/SCOM) vai para a fila da unidade, mas título/categoria/serviço ficam como vieram
    alerta = bool(m.get("alerta")) or is_auto_alert(short, desc, inc.get("caller_id") or "")
    lora = bool(loc and "LORA" in loc)
    is_a4_bool = a4.is_a4(short, desc, inc.get("cmdb_ci") or "") if not alerta else (False, None)
    is_a4 = is_a4_bool[0]
    a4_sistema = is_a4_bool[1]

    fields: dict = {
        "state": "2",
        "assignment_group": final["grupo"],
        "assigned_to": ASSIGNED_TO,
        "u_is_recurring_incident": "no",
    }

    if is_a4:
        # Chamado A4 (UWB, automação, RFID, 4 Olhos, analítico): fila A4, categoria hardware, nota padrão
        fila, grupo = a4.fila_a4_para_unidade(loc) if loc else (None, None)
        if fila and grupo:
            fields["assignment_group"] = grupo
            sigla = m.get("unidade_sigla") or loc.split()[-1][:3].upper()  # fallback: 3 últimas letras
            titulo_a4 = a4.titulo(short, desc, sigla)
            fields["short_description"] = titulo_a4
            fields["category"] = "hardware"
            fields["subcategory"] = "Facilidades"
            fields["u_incident_type"] = TYPE_DEFAULT
            fields["business_service"] = m.get("business_service", BUSINESS_SERVICE)
            if m.get("ic"):
                fields["cmdb_ci"] = m["ic"]
            warnings.append(f"Chamado A4 ({a4_sistema}) → {fila}")
        else:
            warnings.append(f"Chamado A4 ({a4_sistema}): fila não mapeada para {loc}; sem destino.")
    elif not alerta:
        cidade = m.get("cidade") or loc or ""
        title, padrao = build_title(cidade, inc.get("short_description") or "", inc.get("description") or "", lora,
                               inc.get("camera_codigo"))
        if not padrao:
            warnings.append("Título fora do padrão (sem código de câmera/tag reconhecido): confira antes de aprovar.")
        fields.update(
            short_description=title,
            category="hardware" if lora else "network",
            subcategory="Facilidades" if lora else "Telecom",
            u_incident_type=TYPE_LORA if lora else TYPE_DEFAULT,
        )
        if loc == "Serra Azul":
            warnings.append("Serra Azul: business_service (LCB - GESTÃO DE CFTV) sem sys_id mapeado; não enviado.")
        else:
            fields["business_service"] = m.get("business_service", BUSINESS_SERVICE)
        if m.get("ic"):
            fields["cmdb_ci"] = m["ic"]
            if "fallback" in (m.get("ic_nome") or ""):
                warnings.append(f"IC de fallback ({m['ic_nome']}).")
        else:
            warnings.append("IC não mapeado para esta localidade; cmdb_ci não enviado.")
    else:
        warnings.append("Alerta automático: título, categoria e business_service preservados.")

    # Título editado: usar o informado
    if final.get("short_description") and final["short_description"] != inc.get("short_description"):
        fields["short_description"] = final["short_description"]
        warnings.append("Título editado manualmente.")

    for k in ("impact", "urgency"):
        if final.get(k):
            fields[k] = str(final[k])

    # Nota: editada > validação SCOM recente > câmera testada e anexada > padrão (acesso LGPD ou "Encaminhado")
    acesso = not alerta and is_access_request(inc.get("short_description") or "", inc.get("description") or "")
    padrao = WORK_NOTE_ACESSO if acesso else WORK_NOTE
    if acesso:
        warnings.append("Pedido de acesso às câmeras (LGPD): orientar requisição pelo portal; não encerrar.")
    val, cam = contexto.get("scom"), contexto.get("camera")
    if final.get("work_notes"):
        nota = final["work_notes"]
        if nota != padrao:
            warnings.append("Work note editada manualmente.")
    elif alerta and val:
        nota = scom.nota_de(val)
        warnings.append(f"Nota de validação SCOM (ping {val['hora']}, {val['perda']}% de perda); a imagem vai anexada.")
    elif cam and not alerta and not acesso:
        nota = f"{padrao} {camera_line(cam)}"
        warnings.append(f"Nota cita o teste da câmera ({', '.join(cam['codigos'])} às {cam['hora']}).")
    else:
        nota = padrao
    sev = severity_line(final.get("impact"), final.get("urgency"))
    atual = (current.get("work_notes") or "").lower() if current else ""
    if not final.get("work_notes") and nota.splitlines()[0].rstrip(".").lower() in atual:
        warnings.append(f"Work note '{nota[:40]}...' já existe; não será repetida.")
        nota = None
    nota = "\n\n".join(t for t in (nota, sev) if t)
    if nota:
        fields["work_notes"] = nota
    return fields, warnings


def already_in_progress(current: dict | None) -> bool:
    """Em Andamento (state 2) com work note: a skill manda não mexer, só reportar."""
    return bool(current and str(current.get("state")) == "2" and (current.get("work_notes") or "").strip())

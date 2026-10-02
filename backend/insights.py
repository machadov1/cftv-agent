"""Insights da tela de Métricas: o que fazer agora, onde dói e se o agente está ajudando.

Funções puras sobre dados já lidos (backlog do ServiceNow, histórico local, planilha de RITMs, fila local). Nada escreve em
lugar nenhum; cada item traz os números dos incidentes para o painel levar até eles.
"""
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from backend.payload import camera_codes, field_codes, _codes

PARADO_H = 48         # Em Andamento sem nota há mais que isso
RITM_ALERTA_DIAS = 5  # RITM com fechamento nos próximos N dias
MAX_INC = 40          # números listados por cartão

_BRT = timezone(timedelta(hours=-3))


def _dt(s) -> datetime | None:
    """ISO com fuso (backlog) ou 'YYYY-MM-DD HH:MM:SS' em UTC (SQLite)."""
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=_BRT)
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _nota_dt(ultima: str | None) -> datetime | None:
    """'2026-09-30 14:10:03 - Fulano' (horário de Brasília, como o ServiceNow mostra) -> datetime."""
    m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", ultima or "") or \
        re.match(r"(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})", ultima or "")
    if not m:
        return None
    fmt = "%Y-%m-%d %H:%M:%S" if "-" in m.group(1)[:5] else "%d/%m/%Y %H:%M:%S"
    return datetime.strptime(m.group(1), fmt).replace(tzinfo=_BRT)


# ---------------- câmeras ----------------
def area(code: str) -> str:
    """Setor da câmera pelo código: BM-PAT-G-052 -> BM-PAT, BM-LAM-CLI-049 -> BM-LAM-CLI, RES027 -> RES, 03-SUC -> SUC."""
    partes = [p for p in code.upper().split("-") if p and not p.isdigit() and not re.fullmatch(r"[A-Z]", p)]
    partes = [re.sub(r"\d+[A-Z]?$", "", p) or p for p in partes]
    partes = [p for p in partes if not p.isdigit()]
    return "-".join(partes[:3]) if partes else code.upper()


def _status_camera(texto: str) -> str:
    t = texto.lower()
    if t.strip() == "ok":
        return "ok"
    if "desativada" in t:
        return "desativada"
    if "sem sinal" in t:
        return "sem_sinal"
    if "não está" in t or "não encontrada" in t or "ambígua" in t:
        return "nao_achada"
    return "erro"


def diagnostico_cameras(history: list[dict]) -> dict[str, dict]:
    """Último teste no Digifort por incidente: {inc: {cameras: {cod: status}, quando, anexado, nota}}."""
    out: dict[str, dict] = {}
    for h in history:
        n = h["incident_number"]
        d = out.setdefault(n, {"cameras": {}, "quando": None, "anexado": False, "nota": False})
        if h["acao"] == "snapshot":
            cams = {}
            # "COD: texto; COD2: texto" e o texto pode ter "; " ("...Digifort; snapshot não gerado")
            for parte in re.split(r"; (?=[A-Za-z0-9][\w.\-]*: )", h["resultado"] or ""):
                cod, _, txt = parte.partition(": ")
                if cod:
                    cams[cod.strip()] = _status_camera(txt)
            d.update(cameras=cams, quando=h["created_at"])
        elif h["acao"] == "snapshot_anexo":
            d["anexado"] = True
        elif h["acao"] == "nota_encerramento":
            d["nota"] = True
    return out


# ---------------- A. para agir agora ----------------
def onda_sla(rows: list[dict], now: datetime) -> dict:
    """Maior concentração de prazos num dia, com a janela de horário e a quebra por equipe; vencidos à parte."""
    vencidos = [r for r in rows if r["prazo_estado"] == "vencido"]
    por_dia: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        d = _dt(r.get("prazo"))
        if d and r["prazo_estado"] != "vencido":
            por_dia[d.astimezone(_BRT).date().isoformat()].append(r)
    equipes = sorted({r["equipe"] for r in rows})
    serie = []
    for i in range(7):
        dia = (now.astimezone(_BRT).date() + timedelta(days=i)).isoformat()
        c = Counter(r["equipe"] for r in por_dia.get(dia, []))
        serie.append({"dia": dia, **{e: c.get(e, 0) for e in equipes}})
    pico = None
    if por_dia:
        dia, lista = max(por_dia.items(), key=lambda kv: len(kv[1]))
        horas = sorted(_dt(r["prazo"]).astimezone(_BRT) for r in lista)
        pico = {"dia": dia, "total": len(lista), "de": f"{horas[0]:%H:%M}", "ate": f"{horas[-1]:%H:%M}",
                "fracao": round(100 * len(lista) / max(1, len(rows))),
                "por_equipe": [{"equipe": e, "total": n} for e, n in Counter(r["equipe"] for r in lista).most_common()],
                "incidentes": [r["number"] for r in lista][:MAX_INC]}
    return {"pico": pico, "vencidos": [{"number": r["number"], "titulo": r["titulo"], "equipe": r["equipe"],
                                         "prazo_txt": r["prazo_txt"]} for r in vencidos],
            "serie": serie, "equipes": equipes}


def cameras_acao(rows: list[dict], diag: dict[str, dict]) -> dict:
    """Do backlog aberto: câmera já voltou (pode encerrar) e câmera desativada no cadastro (não é campo)."""
    abertos = {r["number"]: r for r in rows}
    voltou, desativada, sem_sinal = [], [], []
    for n, d in diag.items():
        if n not in abertos or not d["cameras"]:
            continue
        st = set(d["cameras"].values())
        item = {"number": n, "titulo": abertos[n]["titulo"], "cameras": d["cameras"], "quando": d["quando"],
                "anexado": d["anexado"]}
        if st == {"ok"} and not d["nota"]:
            voltou.append(item)
        if "desativada" in st:
            desativada.append(item)
        if "sem_sinal" in st:
            sem_sinal.append(item)
    return {"voltou": voltou, "desativada": desativada, "sem_sinal": sem_sinal}


def parados(rows: list[dict], now: datetime) -> dict:
    """Em Andamento sem nota há mais de PARADO_H (ou sem nota nenhuma e aberto há mais que isso)."""
    out = []
    for r in rows:
        if "andamento" not in (r["status"] or "").lower():
            continue
        ref = _nota_dt(r.get("ultima_nota")) or _dt(r.get("aberto"))
        if not ref:
            continue
        h = (now - ref).total_seconds() / 3600
        if h >= PARADO_H:
            out.append({"number": r["number"], "titulo": r["titulo"], "equipe": r["equipe"], "horas": round(h),
                        "ultima_nota": r.get("ultima_nota")})
    out.sort(key=lambda x: -x["horas"])
    return {"total": len(out), "por_equipe": [{"equipe": e, "total": n} for e, n in
                                              Counter(x["equipe"] for x in out).most_common()], "itens": out[:MAX_INC]}


def ritms(rows: list[dict], now: datetime) -> dict:
    """RITMs abertas na planilha: vencendo (<= RITM_ALERTA_DIAS), vencidas e de quem dependemos."""
    hoje = now.astimezone(_BRT).date()
    abertas = [r for r in rows if (r["situacao"] or "").lower().startswith("abert")]
    itens = []
    for r in abertas:
        f = r["fechamento"].date() if r.get("fechamento") else None
        dias = (f - hoje).days if f else None
        itens.append({"ritm": r["ritm"], "inc": r["inc"], "unidade": r["unidade"], "pendencia": r["pendencia"],
                      "descricao": r["descricao"], "fechamento": f.isoformat() if f else None, "dias": dias,
                      "aberta_ha": (hoje - r["abertura"].date()).days if r.get("abertura") else None})
    itens.sort(key=lambda x: (x["dias"] is None, x["dias"] if x["dias"] is not None else 0))
    return {"abertas": len(abertas),
            "vencendo": [x for x in itens if x["dias"] is not None and 0 <= x["dias"] <= RITM_ALERTA_DIAS],
            "vencidas": [x for x in itens if x["dias"] is not None and x["dias"] < 0],
            "por_pendencia": [{"pendencia": p, "total": n} for p, n in Counter(x["pendencia"] or "—" for x in itens).most_common()],
            "por_unidade": [{"unidade": u, "total": n} for u, n in Counter(x["unidade"] or "—" for x in itens).most_common()],
            "itens": itens}


def sem_destino(rows: list[dict], local: list[dict], sugestoes: list[dict]) -> dict:
    back = [r["number"] for r in rows if not r.get("localidade")]
    fila = [i["incident_number"] for i in local if i.get("status") == "analisado" and not i.get("grupo")]
    return {"backlog": back, "fila": fila,
            "sugestoes": [{"prefixo": s["prefixo"], "localidade": s["localidade"], "resolveria": s.get("resolveria_agora", 0),
                           "incidentes": s.get("incidentes")} for s in sugestoes]}


# ---------------- B. onde dói ----------------
def _cameras_por_incidente(rows: list[dict], local: list[dict], ritm_rows: list[dict]) -> list[tuple[str, str, str, str]]:
    """(câmera, incidente, unidade, fonte) de backlog, fila local e RITMs; sem alertas SCOM nem LORA."""
    out, vistos = [], set()
    for i in local:
        loc = i.get("localidade") or ""
        if "LORA" in loc or "Projects" in loc:
            continue
        for c in camera_codes(i.get("camera_codigo"), i.get("short_description") or "", i.get("description") or ""):
            out.append((c, i["incident_number"], loc, "fila"))
            vistos.add((c, i["incident_number"]))
    for r in rows:
        loc = r.get("localidade") or ""
        if "LORA" in loc or "Projects" in loc or "LORA" in (r.get("grupo") or ""):
            continue
        for c in camera_codes(None, r["titulo"] or "", r.get("descricao") or ""):
            if (c, r["number"]) not in vistos:
                out.append((c, r["number"], loc, "backlog"))
                vistos.add((c, r["number"]))
    for r in ritm_rows:
        for c in dict.fromkeys(_codes(r.get("descricao") or "") + field_codes(r.get("descricao") or "")):
            if (c, r["inc"]) not in vistos:
                out.append((c, r["inc"], r.get("unidade") or "", f"RITM {r.get('ritm')}"))
                vistos.add((c, r["inc"]))
    return out


def pontos_quentes(cams: list[tuple[str, str, str, str]]) -> list[dict]:
    """Setores (prefixo do código) com mais câmeras distintas/incidentes."""
    g: dict[str, dict] = {}
    for c, n, loc, _ in cams:
        a = area(c)
        if not re.search(r"[A-Z]", a):
            continue
        x = g.setdefault(a, {"area": a, "cameras": set(), "incidentes": set(), "unidades": Counter()})
        x["cameras"].add(c)
        x["incidentes"].add(n)
        if loc:
            x["unidades"][loc] += 1
    out = [{"area": x["area"], "unidade": (x["unidades"].most_common(1) or [("", 0)])[0][0],
            "cameras": sorted(x["cameras"]), "incidentes": sorted(x["incidentes"])} for x in g.values()]
    out = [x for x in out if len(x["incidentes"]) >= 2]
    out.sort(key=lambda x: (-len(x["incidentes"]), -len(x["cameras"])))
    return out[:8]


def cameras_cronicas(cams: list[tuple[str, str, str, str]]) -> list[dict]:
    """Mesma câmera em 2+ incidentes (fila, backlog ou RITM): pede causa raiz/RITM, não mais um incidente."""
    g: dict[str, dict] = {}
    for c, n, loc, fonte in cams:
        x = g.setdefault(c, {"camera": c, "unidade": loc, "incidentes": {}})
        x["incidentes"].setdefault(n, fonte)
        x["unidade"] = x["unidade"] or loc
    out = [{"camera": x["camera"], "unidade": x["unidade"],
            "incidentes": [{"number": n, "fonte": f} for n, f in x["incidentes"].items()]}
           for x in g.values() if len(x["incidentes"]) >= 2]
    out.sort(key=lambda x: -len(x["incidentes"]))
    return out[:10]


def lora(rows: list[dict], now: datetime) -> dict:
    """Lote LORA aberto: tamanho, idade e tags repetidas em mais de um incidente."""
    itens = [r for r in rows if "LORA" in (r.get("grupo") or "") or "LORA" in (r["titulo"] or "").upper()]
    tags: dict[str, list[str]] = defaultdict(list)
    for r in itens:
        for t in dict.fromkeys(re.findall(r"(?<!\d)\d{3,4}(?!\d)", f"{r['titulo']} {r.get('descricao') or ''}")):
            tags[t].append(r["number"])
    idades = [(now - _dt(r["aberto"])).total_seconds() / 86400 for r in itens if _dt(r.get("aberto"))]
    return {"total": len(itens), "de": len(rows), "idade_media_d": round(statistics.mean(idades), 1) if idades else None,
            "mais_antigo_d": round(max(idades), 1) if idades else None,
            "tags_repetidas": sorted(({"tag": t, "incidentes": ns} for t, ns in tags.items() if len(ns) > 1),
                                     key=lambda x: -len(x["incidentes"]))[:10]}


# ---------------- C. o agente está ajudando? ----------------
def agente(local: list[dict], history: list[dict]) -> dict:
    """Da chegada no ServiceNow ao despacho; despachos sem edição; análises sem LLM; reanálises."""
    abertos = {i["incident_number"]: _dt(i.get("opened_at")) for i in local}
    desp, editados, analises, llm = [], 0, Counter(), 0
    for h in history:
        if h["acao"] in ("aprovado", "editado"):
            ini, fim = abertos.get(h["incident_number"]), _dt(h["created_at"])
            if ini and fim and fim > ini:
                desp.append((fim - ini).total_seconds() / 3600)
            editados += h["acao"] == "editado"
        elif h["acao"] == "analise":
            analises[h["incident_number"]] += 1
            llm += bool(h["chamou_claude"])
    total_desp = len([h for h in history if h["acao"] in ("aprovado", "editado")])
    n_an = sum(analises.values())
    return {"despachados": total_desp,
            "mediana_ate_despacho_h": round(statistics.median(desp), 1) if desp else None,
            "sem_edicao_pct": round(100 * (total_desp - editados) / total_desp) if total_desp else None,
            "sem_llm_pct": round(100 * (n_an - llm) / n_an) if n_an else None,
            "reanalises_media": round(n_an / len(analises), 1) if analises else None,
            "testes_camera": sum(h["acao"] == "snapshot" for h in history),
            "ritms": sum(h["acao"] == "ritm" for h in history)}


def tendencia(snaps: list[dict]) -> dict:
    """Série diária do backlog com entradas/saídas (diferença dos números com o dia anterior)."""
    serie, antes = [], None
    for s in snaps:
        atual = set(s["numeros"])
        serie.append({"dia": s["dia"], "total": s["total"], "vencidos": s["vencidos"], "idade_media_h": s["idade_media_h"],
                      "entraram": len(atual - antes) if antes is not None else None,
                      "sairam": len(antes - atual) if antes is not None else None})
        antes = atual
    return {"serie": serie, "coletando_desde": snaps[0]["dia"] if snaps else None, "pontos": len(serie)}


def painel(backlog: dict | None, history: list[dict], ritm_rows: list[dict], local: list[dict], sugestoes: list[dict],
           snaps: list[dict], now: datetime) -> dict:
    rows = (backlog or {}).get("rows") or []
    diag = diagnostico_cameras(history)
    cams = _cameras_por_incidente(rows, local, ritm_rows)
    return {
        "atualizado_em": now.isoformat(),
        "backlog_total": len(rows),
        "agir": {"onda": onda_sla(rows, now), "cameras": cameras_acao(rows, diag), "parados": parados(rows, now),
                 "ritms": ritms(ritm_rows, now), "sem_destino": sem_destino(rows, local, sugestoes)},
        "doi": {"pontos_quentes": pontos_quentes(cams), "cronicas": cameras_cronicas(cams), "lora": lora(rows, now)},
        "agente": {**agente(local, history), "tendencia": tendencia(snaps)},
    }

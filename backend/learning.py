"""Aprendizado leve: o prefixo do código da câmera (BM-LAM-CLI-048 -> BM) indica a unidade.

Só sugere regras a partir de incidentes já com localidade definida (regra forte, campo do ServiceNow ou decisão sua).
Nada vira regra sem você aceitar; aceitar também reaplica o novo padrão aos incidentes que estavam sem destino.
"""
import re
from collections import Counter, defaultdict

from backend import db
from backend.payload import camera_codes
from backend.rules_engine import engine

MIN_INCIDENTES = 2
MIN_PUREZA = 0.8
_PREFIXO = re.compile(r"^([A-Za-z]{2,5})(?=[-_.\d])")


def prefixo(code: str) -> str | None:
    m = _PREFIXO.match(code or "")
    return m.group(1).upper() if m else None


def _prefixos(row: dict) -> set[str]:
    cods = camera_codes(row.get("camera_codigo"), row.get("short_description") or "", row.get("description") or "")
    return {p for p in (prefixo(c) for c in cods) if p}


def _regex(pref: str) -> str:
    return rf"(?<![A-Za-z]){pref}(?=[-_.\d])"


def _coberto(pref: str) -> bool:
    """Alguma regra com localidade já casa com esse prefixo?"""
    amostra = f"{pref}-000"
    for r in engine.rules:
        if not r.get("localidade"):
            continue
        try:
            if r.get("pattern") and re.search(r["pattern"], amostra, re.IGNORECASE):
                return True
        except re.error:
            continue
    return False


def sugestoes() -> list[dict]:
    rows = db.list_incidents(limit=10000, only_pending=False)  # Todos, para aprender
    por_pref: dict[str, Counter] = defaultdict(Counter)
    exemplos: dict[str, list] = defaultdict(list)
    sem_destino: Counter = Counter()
    for r in rows:
        prefs = _prefixos(r)
        loc = r.get("localidade")
        for p in prefs:
            if not loc:
                sem_destino[p] += 1
            elif "LORA" not in loc and ((r.get("localidade_confianca") or 0) >= 85 or r.get("status") == "aprovado"):
                por_pref[p][loc] += 1
                if len(exemplos[p]) < 3:
                    exemplos[p].append(r["incident_number"])

    out = []
    for p, cont in por_pref.items():
        loc, n = cont.most_common(1)[0]
        total = sum(cont.values())
        if total < MIN_INCIDENTES or n / total < MIN_PUREZA or _coberto(p):
            continue
        grupo, grupo_display = engine.find_group_for_localidade(loc)
        out.append({
            "prefixo": p, "localidade": loc, "incidentes": total, "pureza": round(n / total * 100),
            "exemplos": exemplos[p], "resolveria_agora": sem_destino.get(p, 0),
            "grupo_display": grupo_display, "pode_criar": bool(grupo),
            "regra": {"pattern": _regex(p), "localidade": loc, "grupo": grupo, "grupo_display": grupo_display},
        })
    return sorted(out, key=lambda s: (-s["resolveria_agora"], -s["incidentes"]))


def regra_para(pref: str, localidade: str) -> dict:
    """Corpo da regra nova (atributos copiados da regra existente da mesma localidade)."""
    grupo, grupo_display = engine.find_group_for_localidade(localidade)
    if not grupo:
        raise ValueError(f"'{localidade}' não tem grupo numa regra existente; crie a regra manualmente")
    base = next((r for r in engine.rules if r.get("localidade") == localidade), {})
    return {"pattern": _regex(pref.upper()), "localidade": localidade, "grupo": grupo, "grupo_display": grupo_display,
            "ritm_necessaria": bool(base.get("ritm_necessaria")), "categoria": base.get("categoria"),
            "subcategory": base.get("subcategory"), "pendencia": None}


def localidade_por_camera(camera_codigo: str | None) -> str | None:
    """Se o código da câmera começa com um prefixo de unidade conhecida, retorna a localidade.
    Ex: 'BM-PAT-A-058' → 'Barra Mansa' (se BM estiver numa regra)."""
    if not camera_codigo:
        return None
    pref = prefixo(camera_codigo)
    if not pref:
        return None
    # Procura uma regra que case com esse prefixo
    for r in engine.rules:
        if r.get("localidade") and r.get("pattern"):
            try:
                if re.search(rf"(?<![A-Za-z]){pref}(?=[-_.\d])", r["pattern"], re.IGNORECASE):
                    return r["localidade"]
            except re.error:
                continue
    return None


def reaplicar_sem_destino() -> list[str]:
    """Reaplica as regras (agora com o código da câmera) aos incidentes pendentes sem localidade."""
    atualizados = []
    for r in db.list_incidents(limit=10000):
        if r.get("localidade") or r.get("status") != "analisado":
            continue
        res = engine.apply_rules(r)
        # Se ainda sem localidade, tenta pelo prefixo da câmera
        if not res["localidade"] and r.get("camera_codigo"):
            cam_loc = localidade_por_camera(r["camera_codigo"])
            if cam_loc:
                # Preenche os dados da localidade
                res["localidade"] = cam_loc
                for rule in engine.rules:
                    if rule.get("localidade") == cam_loc and rule.get("grupo"):
                        res["grupo"] = rule["grupo"]
                        res["grupo_display"] = rule.get("grupo_display")
                        break
                res["motivo"] = f"Câmera {r['camera_codigo']} (prefixo {r['camera_codigo'][:2]})"
        if res["localidade"]:
            db.update_routing(r["incident_number"], res)
            atualizados.append(r["incident_number"])
    return atualizados

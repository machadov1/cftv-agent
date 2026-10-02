import os
import re
import unicodedata
from backend.db import get_rules
from backend.config import config
from backend import pistas as pistas_mod


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower().strip()

class RulesEngine:
    """Regras determinísticas.

    - Regra com `localidade` define localidade/grupo (a primeira que casar vence).
    - Regra sem `localidade` (ex.: fibra rompida) só contribui com RITM/categoria/pendência.
    """

    def __init__(self):
        self._mtime = None
        self._rules = []

    @property
    def rules(self) -> list:
        # Recarrega quando data/rules.json muda (edição via dashboard ou manual)
        mtime = os.path.getmtime(config.RULES_PATH)
        if mtime != self._mtime:
            self._rules = get_rules()["rules"]
            self._mtime = mtime
        return self._rules

    def apply_rules(self, incident: dict) -> dict:
        """Aplicar regras determinísticas ao incidente"""
        text = (f"{incident.get('short_description') or ''} {incident.get('description') or ''} "
                f"{incident.get('camera_codigo') or ''}")

        result = {
            "localidade": None,
            "localidade_confianca": 0,
            "grupo": None,
            "grupo_display": None,
            "ritm_necessaria": False,
            "categoria": None,
            "pendencia": None,
            "motivo": "",
        }
        motivos = []

        # Pistas fora do texto (IC afetado, local do IC/solicitante). Alerta automático (TrueSight/SCOM, banda...): a
        # unidade é a do servidor (texto "on computer X" ou nome do IC), não Projects; Projects só para host PRJ/sem unidade.
        pistas = pistas_mod.coletar(incident)
        result["pistas"] = pistas
        top = pistas_mod.melhor(pistas)
        if top and top["peso"] >= pistas_mod.PESO_HOST and top["unidade"] in self.known_localidades():
            grupo, grupo_display = self.find_group_for_localidade(top["unidade"])
            result.update(localidade=top["unidade"], localidade_confianca=100, grupo=grupo, grupo_display=grupo_display)
            motivos.append(f"{top['fonte']} {top['valor']} → {top['unidade']}")

        for rule in self.rules:
            pattern = rule.get("pattern") or ""
            try:
                if not pattern or not re.search(pattern, text, re.IGNORECASE):
                    continue
            except re.error:
                continue

            if rule.get("localidade"):
                if result["localidade"]:
                    continue
                result["localidade"] = rule["localidade"]
                result["localidade_confianca"] = 100
                result["grupo"] = rule.get("grupo")
                result["grupo_display"] = rule.get("grupo_display")
            result["ritm_necessaria"] = result["ritm_necessaria"] or bool(rule.get("ritm_necessaria"))
            result["categoria"] = result["categoria"] or rule.get("categoria")
            result["pendencia"] = result["pendencia"] or rule.get("pendencia")
            motivos.append(f"regra #{rule.get('id')} ({pattern})")

        if motivos:
            result["motivo"] = "Match: " + "; ".join(motivos)

        # Se nenhuma localidade foi identificada, tentar usar u_incident_location (localidade do incidente no SN)
        if not result["localidade"]:
            raw_location = (incident.get("u_incident_location") or "").strip()
            location = _norm(raw_location)
            if location:
                # Campo vem livre ("Sabara", "CFTV - Monlevade"): vale o padrão da regra ou o nome sem acento
                for rule in self.rules:
                    rule_loc = _norm(rule.get("localidade") or "")
                    if not rule_loc or "lora" in rule_loc:
                        continue
                    try:
                        by_pattern = bool(rule.get("pattern") and re.search(rule["pattern"], raw_location, re.IGNORECASE))
                    except re.error:
                        by_pattern = False
                    if by_pattern or rule_loc in location or location in rule_loc:
                        result["localidade"] = rule["localidade"]
                        result["localidade_confianca"] = 85  # Um pouco menor que regex (100)
                        result["grupo"] = rule.get("grupo")
                        result["grupo_display"] = rule.get("grupo_display")
                        motivos.append(f"u_incident_location match: {rule.get('localidade')}")
                        break

        # Sem localidade pelo texto/campo: a pista mais forte (IC, local do IC, local do solicitante) decide
        if not result["localidade"] and top and top["unidade"] in self.known_localidades():
            grupo, grupo_display = self.find_group_for_localidade(top["unidade"])
            result.update(localidade=top["unidade"], localidade_confianca=top["peso"], grupo=grupo,
                          grupo_display=grupo_display)
            motivos.append(f"pista: {top['fonte']} {top['valor']} → {top['unidade']}")
        # IC apontando para outra unidade que a decidida pelo texto: não despachar sem olhar
        elif result["localidade"] and not (top and top["peso"] >= pistas_mod.PESO_HOST):
            contra = [p for p in pistas_mod.conflitos(pistas, result["localidade"])
                      if p["fonte"] in ("IC afetado", "local do IC")]
            if contra:
                result["localidade_confianca"] = min(result["localidade_confianca"], 60)
                result["conflito"] = True
                motivos.append("conflito: " + ", ".join(f"{p['fonte']} {p['valor']} → {p['unidade']}" for p in contra))

        if motivos:
            result["motivo"] = "Match: " + "; ".join(motivos)
        if not result["localidade"]:
            result["motivo"] = (result["motivo"] + " | " if result["motivo"] else "") \
                + "Localidade não identificada - LLM necessário"
        return result

    def find_group_for_localidade(self, localidade: str) -> tuple[str | None, str | None]:
        """(grupo, grupo_display) da regra dessa localidade, se existir"""
        for rule in self.rules:
            if rule.get("localidade") == localidade and rule.get("grupo"):
                return rule["grupo"], rule.get("grupo_display")
        return None, None

    def known_localidades(self) -> list[str]:
        seen = []
        for rule in self.rules:
            loc = rule.get("localidade")
            if loc and "LORA" not in loc and loc not in seen:
                seen.append(loc)
        return seen

engine = RulesEngine()

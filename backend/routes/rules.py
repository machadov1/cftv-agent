from fastapi import APIRouter, HTTPException
from backend.db import get_rules, save_rules
from backend.models import RuleIn
from backend import learning
from backend.rules_engine import engine
from pydantic import BaseModel


class AceitarIn(BaseModel):
    prefixo: str
    localidade: str

router = APIRouter(prefix="/rules", tags=["rules"])

@router.get("")
def list_rules():
    """Listar todas as regras"""
    return get_rules()["rules"]

@router.get("/destinos")
def destinos():
    """Localidades com fila conhecida (uma por localidade), para escolher o destino na edição manual."""
    vistos, out = set(), []
    for r in engine.rules:
        loc = r.get("localidade")
        if loc and r.get("grupo") and loc not in vistos:
            vistos.add(loc)
            out.append({"localidade": loc, "grupo": r["grupo"], "grupo_display": r.get("grupo_display"),
                        "ritm_necessaria": bool(r.get("ritm_necessaria"))})
    return sorted(out, key=lambda d: d["localidade"])

@router.get("/sugestoes")
def sugestoes():
    """Regras sugeridas pelo que já foi aprendido (prefixo do código da câmera -> unidade). Não cria nada."""
    return learning.sugestoes()

@router.post("/sugestoes/aceitar", status_code=201)
def aceitar_sugestao(body: AceitarIn):
    """Cria a regra sugerida e reaplica aos pendentes sem localidade."""
    try:
        new = learning.regra_para(body.prefixo, body.localidade)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    rules = get_rules()
    new["id"] = max([r.get("id", 0) for r in rules["rules"]], default=0) + 1
    rules["rules"].append(new)
    save_rules(rules)
    engine._mtime = None
    return {"regra": new, "reaplicados": learning.reaplicar_sem_destino()}

@router.post("", status_code=201)
def create_rule(rule: RuleIn):
    """Criar nova regra"""
    rules = get_rules()
    new = rule.model_dump()
    new["id"] = max([r.get("id", 0) for r in rules["rules"]], default=0) + 1
    rules["rules"].append(new)
    save_rules(rules)
    return new

@router.put("/{rule_id}")
def update_rule(rule_id: int, updated_rule: RuleIn):
    """Atualizar regra existente"""
    rules = get_rules()
    for rule in rules["rules"]:
        if rule["id"] == rule_id:
            rule.update(updated_rule.model_dump())
            save_rules(rules)
            return rule
    raise HTTPException(status_code=404, detail="Regra não encontrada")

@router.delete("/{rule_id}")
def delete_rule(rule_id: int):
    """Remover regra"""
    rules = get_rules()
    remaining = [r for r in rules["rules"] if r["id"] != rule_id]
    if len(remaining) == len(rules["rules"]):
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    rules["rules"] = remaining
    save_rules(rules)
    return {"ok": True}

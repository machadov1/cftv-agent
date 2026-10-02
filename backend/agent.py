"""Agente de chat do console: entende pedidos em texto e prints, consulta o ServiceNow (SOMENTE LEITURA)
e devolve PROPOSTAS de ação. Nenhuma escrita acontece aqui: o analista confirma na tela, e a execução
passa pelo mesmo caminho do botão Despachar (dry-run, checagem de duplicidade)."""
import json
import re
import time

from fastapi import HTTPException

from backend import backlog, db, llm, intents
from backend.analysis import analyze
from backend.payload import display_title, relevant_text
from backend.servicenow_api import SNAuthError, sn_api

MAX_STEPS = 6
ESTADOS = {"1": "Novo", "2": "Em Andamento", "3": "Em Espera", "4": "Aguardando Info do Usuário", "5": "Aguardando Evidência",
           "6": "Resolvido", "7": "Encerrado", "8": "Aguardando Mudança", "9": "Aguardando Fornecedor", "24": "Cancelado"}
MAX_BATCH = 20
_INC = re.compile(r"\bINC\d{6,8}\b", re.I)

SYSTEM = """Você é o agente de CFTV do Victor (Grupo Alert / ArcelorMittal), dentro do console CFTV Agent.
Responda em português do Brasil, curto e direto, sem floreio.

O que você pode fazer (ferramentas, todas só de LEITURA no ServiceNow):
- listar_fila: ver incidentes abertos nas filas CFTV/A4/LORA (filtra por equipe, estado, texto).
- consultar_incidentes: ler e analisar incidentes pelo número (localidade, fila sugerida, título no padrão, bloqueios).
- propor_primeira_tratativa: montar a proposta de primeira tratativa (Em Andamento + fila + título + work note) para confirmação do Victor.

Regras absolutas (skill operador-cftv):
1. Você NÃO grava nada. Ações só viram proposta; o Victor confirma na tela.
2. Nunca propor encerramento, comentário ao usuário nem envio de Teams.
3. Localidade incerta = não mover: diga o motivo. Serra Azul só com OK explícito do Victor.
4. Não mexer em incidente fora de CFTV (RFID de empilhadeira, Safe Zone) nem em incidente já Em Andamento em outra fila: só reportar.
5. Nunca invente número de incidente, sys_id, grupo ou dado: use as ferramentas. Se um número do print não existir, diga.
6. Em lote (print com vários incidentes do mesmo teor), consulte todos antes de propor, e separe os que não podem ser tratados.

Ao informar estado, prazo ou fila, copie exatamente os campos 'estado', 'prazo' e 'fila_atual' das ferramentas; nunca deduza.
Só proponha tratativa para incidente em estado Novo, a não ser que o Victor peça outra coisa.

"Tratar" um incidente novo = primeira tratativa (propor_primeira_tratativa). Equipes: JDF, MDE, PIR (Piracicaba), RSD (Resende), BMA (Barra Mansa), PEC, LORA, A4, 4 OLHOS, Geral (fila AMS-TI-CFTV).
Incidente novo de uma unidade costuma chegar na fila Geral com título genérico: para 'fila de <cidade>', use listar_fila com localidade=<cidade> (sem equipe), além da equipe da unidade.
Para chamar ferramentas use o mecanismo de tool calls; nunca escreva a chamada como texto."""

TOOLS = [
    {"type": "function", "function": {
        "name": "listar_fila",
        "description": "Lista incidentes abertos das filas CFTV (board do Victor), ordenados por prazo.",
        "parameters": {"type": "object", "properties": {
            "equipe": {"type": "string", "description": "JDF, MDE, PIR, RSD, BMA, PEC, LORA, A4, 4 OLHOS, Geral ou Outras"},
            "estado": {"type": "string", "description": "Novo ou Em Andamento"},
            "localidade": {"type": "string", "description": "unidade inferida pelas regras (ex.: Piracicaba, Resende, Barra Mansa)"},
            "texto": {"type": "string", "description": "trecho do título, da descrição ou do nome da fila (ex.: PR421, LORA 808)"},
            "limite": {"type": "integer", "description": "máximo de itens (padrão 15)"}}}}},
    {"type": "function", "function": {
        "name": "consultar_incidentes",
        "description": "Lê do ServiceNow e analisa um ou mais incidentes pelo número (INC...).",
        "parameters": {"type": "object", "properties": {
            "numeros": {"type": "array", "items": {"type": "string"}}}, "required": ["numeros"]}}},
    {"type": "function", "function": {
        "name": "propor_primeira_tratativa",
        "description": "Monta a proposta de primeira tratativa para os incidentes (não grava; o Victor confirma na tela).",
        "parameters": {"type": "object", "properties": {
            "numeros": {"type": "array", "items": {"type": "string"}}}, "required": ["numeros"]}}},
]


def _norm(n: str) -> str | None:
    m = _INC.search(n or "")
    return m.group(0).upper() if m else None


# ---------------- ferramentas ----------------
def t_listar_fila(equipe: str | None = None, estado: str | None = None, texto: str | None = None, limite: int = 15,
                  localidade: str | None = None):
    data = backlog.get_backlog()
    rows = data["rows"]
    if localidade:
        lc = localidade.strip().lower()
        rows = [r for r in rows if lc in (r.get("localidade") or "").lower()]
    if equipe:
        rows = [r for r in rows if r["equipe"].lower() == equipe.strip().lower()]
    if estado:
        rows = [r for r in rows if (r["status"] or "").lower() == estado.strip().lower()]
    if texto:
        t = texto.strip().lower()
        rows = [r for r in rows if t in f"{r['titulo']} {r['grupo']} {r.get('localidade') or ''} {r.get('descricao') or ''}".lower()]
    limite = max(1, min(int(limite or 15), 40))
    return {"total": len(rows), "itens": [{k: r.get(k) for k in ("number", "titulo", "status", "grupo", "equipe", "localidade", "prazo_txt", "sla_violado")}
                                          for r in rows[:limite]]}


def t_consultar(numeros: list[str]):
    out = []
    try:  # estado, prazo e fila por extenso (o modelo erra ao traduzir códigos)
        abertos = {r["number"]: r for r in backlog.get_backlog()["rows"]}
    except Exception:  # noqa: BLE001
        abertos = {}
    for n in list(dict.fromkeys(filter(None, (_norm(x) for x in numeros))))[:MAX_BATCH]:
        sn = sn_api.get_incident(n)
        if not sn:
            out.append({"numero": n, "existe": False})
            continue
        # Só entra na fila local de aprovação o que ainda é Novo; o resto é analisado sem gravar
        novo = str(sn.get("state")) == "1"
        a = analyze(n, sn, allow_llm=False, persist=novo)
        t = display_title({**sn, "localidade": a["localidade"]})
        out.append({
            "numero": n, "existe": True,
            "titulo_original": sn.get("short_description"),
            "titulo_padrao": t["titulo_padrao"],
            "descricao": relevant_text(sn.get("description") or "")[:500],
            "estado": ESTADOS.get(str(sn.get("state")), str(sn.get("state"))),
            "prazo": (abertos.get(n) or {}).get("prazo_txt"),
            "fila_atual": (abertos.get(n) or {}).get("grupo"),
            "sla_violado": (abertos.get(n) or {}).get("sla_violado"),
            "localidade": a["localidade"], "confianca": a["localidade_confianca"],
            "fila_sugerida": a["grupo_display"], "ritm": a["ritm_necessaria"], "pendencia": a["pendencia"],
            "bloqueio": None if a["grupo"] else (a["pendencia"] or "sem localidade/fila definida"),
        })
    return {"incidentes": out}


def t_propor(numeros: list[str], _actions: list):
    from backend.routes.incidents import _prepare  # mesmas checagens do botão Despachar
    itens = []
    for n in list(dict.fromkeys(filter(None, (_norm(x) for x in numeros))))[:MAX_BATCH]:
        if not db.get_incident(n):
            sn = sn_api.get_incident(n)
            if not sn:
                itens.append({"numero": n, "ok": False, "motivo": "não existe no ServiceNow"})
                continue
            if str(sn.get("state")) != "1":
                itens.append({"numero": n, "ok": False,
                              "motivo": f"já está {ESTADOS.get(str(sn.get('state')), sn.get('state'))}: primeira tratativa só para Novo"})
                continue
            analyze(n, sn)
        try:
            inc, _c, _e, fields, warnings, _anexo = _prepare(n, None)
            itens.append({"numero": n, "ok": True, "titulo": fields.get("short_description") or inc.get("short_description"),
                          "fila": inc.get("grupo_display"), "avisos": warnings})
        except HTTPException as e:
            itens.append({"numero": n, "ok": False, "motivo": e.detail})
    _actions.append({"tipo": "primeira_tratativa", "itens": itens})
    return {"proposta_registrada": True, "prontos": sum(i["ok"] for i in itens), "bloqueados": [i for i in itens if not i["ok"]],
            "observacao": "Nada foi gravado. O Victor confirma na tela."}


def _handle_shortcut(intent_result: dict, trace: list, actions: list) -> dict | None:
    """Executa atalho reconhecido pelo roteador. Retorna resposta pronta ou None se não conseguir."""
    acao = intent_result.get("acao")
    t0 = time.perf_counter()

    if acao == "ajuda":
        reply = (
            "**Atalhos disponíveis:**\n\n"
            "• `trate os novos de [cidade]` → lista e propõe tratativa\n"
            "• `tratar INC123 INC456` → propõe números específicos\n"
            "• `fila [equipe] [estado/prazo]` → ex.: `fila PIR vencem hoje`\n"
            "• `consulte INC123` → mostra destino da IA\n\n"
            "**Ou:** cole um print (Ctrl+V) e descreva o que quer em texto livre."
        )
        return {
            "reply": reply,
            "trace": trace + [{"tipo": "atalho", "acao": "ajuda", "ms": int((time.perf_counter() - t0) * 1000)}],
            "actions": actions,
            "provider": "atalho",
            "model": "regras",
            "ms": int((time.perf_counter() - t0) * 1000),
        }

    if acao == "listar_e_propor":
        localidade = intent_result.get("localidade")
        estado = intent_result.get("estado", "Novo")
        try:
            data = backlog.get_backlog()
            rows = data.get("rows", [])
            if localidade:
                rows = [r for r in rows if r.get("localidade") == localidade]
            if estado:
                rows = [r for r in rows if r.get("status") == estado]
            if not rows:
                return {
                    "reply": f"Nenhum incidente {estado or 'aberto'}{f' em {localidade}' if localidade else ''}.",
                    "trace": trace,
                    "actions": actions,
                    "provider": "atalho",
                    "model": "regras",
                    "ms": int((time.perf_counter() - t0) * 1000),
                }
            numeros = [r["number"] for r in rows[:10]]  # Máx 10
            result = t_propor(numeros, actions)
            return {
                "reply": f"Encontrei {len(rows)} incidentes. Proposta de primeira tratativa:",
                "trace": trace,
                "actions": actions,
                "provider": "atalho",
                "model": "regras",
                "ms": int((time.perf_counter() - t0) * 1000),
            }
        except Exception as e:
            return None  # Cai no LLM

    if acao == "propor":
        numeros = intent_result.get("numeros", [])
        try:
            result = t_propor(numeros, actions)
            return {
                "reply": f"Preparei a proposta para {len(numeros)} incidente(s).",
                "trace": trace,
                "actions": actions,
                "provider": "atalho",
                "model": "regras",
                "ms": int((time.perf_counter() - t0) * 1000),
            }
        except Exception:
            return None

    if acao == "listar_fila":
        try:
            result = t_listar_fila(
                equipe=intent_result.get("equipe"),
                estado=intent_result.get("estado"),
                localidade=intent_result.get("localidade"),
                limite=15,
            )
            total = result.get("total", 0)
            itens_txt = "\n".join(
                f"  • {i['number']} → {i['equipe']} ({i['prazo_txt']})" for i in result.get("itens", [])[:5]
            )
            return {
                "reply": f"**{total} incidente(s)** na fila:\n\n{itens_txt}",
                "trace": trace,
                "actions": actions,
                "provider": "atalho",
                "model": "regras",
                "ms": int((time.perf_counter() - t0) * 1000),
            }
        except Exception:
            return None

    if acao == "consultar":
        numeros = intent_result.get("numeros", [])
        try:
            result = t_consultar(numeros)
            reply = "**Consulta de incidentes:**\n\n"
            for inc in result.get("incidentes", []):
                if inc.get("existe"):
                    reply += f"• **{inc['numero']}** → {inc['fila_sugerida']} ({inc['confianca']}% confiança)\n"
                else:
                    reply += f"• **{inc['numero']}** — não encontrado\n"
            return {
                "reply": reply,
                "trace": trace,
                "actions": actions,
                "provider": "atalho",
                "model": "regras",
                "ms": int((time.perf_counter() - t0) * 1000),
            }
        except Exception:
            return None

    return None

def _exec(name: str, args: dict, actions: list):
    if name == "listar_fila":
        return t_listar_fila(**{k: v for k, v in args.items() if k in ("equipe", "estado", "texto", "limite", "localidade")})
    if name == "consultar_incidentes":
        return t_consultar(args.get("numeros") or [])
    if name == "propor_primeira_tratativa":
        return t_propor(args.get("numeros") or [], actions)
    return {"erro": f"ferramenta desconhecida: {name}"}


# ---------------- visão: print -> texto ----------------
def transcribe(images: list[str]) -> dict:
    content = [{"type": "text", "text": (
        "Transcreva o que é relevante nesta(s) captura(s) de tela do ServiceNow: para cada incidente visível, uma linha "
        "'INC... | título/descrição | fila | estado'. Se não houver lista, descreva o que a tela mostra em até 5 linhas. "
        "Não invente números: se não conseguir ler um dígito, escreva '?'.")}]
    content += [{"type": "image_url", "image_url": {"url": u}} for u in images]
    r = llm.chat([{"role": "user", "content": content}], max_tokens=1500)
    return {"texto": (r["message"].get("content") or "").strip(), "provider": r["provider"], "model": r["model"], "ms": r["ms"]}


_NAMES = {t["function"]["name"] for t in TOOLS}


def _text_tool_calls(content: str) -> list[dict]:
    """Recupera chamadas de ferramenta escritas como JSON no texto (alguns modelos gratuitos fazem isso)."""
    if not content or not any(n in content for n in _NAMES):
        return []
    dec, i, found = json.JSONDecoder(), 0, []
    while i < len(content):
        mm = re.compile(r"[\[{]").search(content, i)
        if not mm:
            break
        j = mm.start()
        try:
            obj, end = dec.raw_decode(content[j:])
        except ValueError:
            i = j + 1
            continue
        i = j + end
        for o in obj if isinstance(obj, list) else [obj]:
            if not isinstance(o, dict):
                continue
            fn = o.get("function") if isinstance(o.get("function"), dict) else {}
            name = o.get("tool_name") or o.get("name") or fn.get("name") or (o.get("function") if isinstance(o.get("function"), str) else None)
            args = o.get("parameters") or o.get("arguments") or o.get("args") or fn.get("arguments") or {}
            if name in _NAMES:
                found.append({"id": f"txt{len(found)}", "type": "function",
                              "function": {"name": name, "arguments": args if isinstance(args, str) else json.dumps(args)}})
    return found


# ---------------- laço ----------------
def run(history: list[dict], images: list[str] | None = None) -> dict:
    """history: [{role: user|assistant, content: str}]; a última é do usuário. images: data URLs do último pedido."""
    t0 = time.perf_counter()
    trace, actions = [], []
    msgs = [{"role": "system", "content": SYSTEM}]
    msgs += [{"role": m["role"], "content": m["content"]} for m in history[:-1] if m.get("content")]
    pedido = history[-1]["content"] if history else ""

    if images:
        try:
            tr = transcribe(images)
        except llm.LLMError as e:
            return {"reply": f"Não consegui ler o print: {e}", "trace": trace, "actions": [], "ms": 0}
        trace.append({"tipo": "visao", "modelo": tr["model"], "ms": tr["ms"], "texto": tr["texto"]})
        nums = sorted(set(m.upper() for m in _INC.findall(tr["texto"])))
        pedido = f"{pedido or 'Veja o print.'}\n\n[Transcrição do print anexado]\n{tr['texto']}\n[Números lidos: {', '.join(nums) or 'nenhum'}]"
    msgs.append({"role": "user", "content": pedido})

    # Tentar resolver pelo roteador de atalhos (sem LLM, < 1s)
    intent_result = intents.run(pedido)
    if intent_result and intent_result.get("via") == "atalho":
        reply = _handle_shortcut(intent_result, trace, actions)
        if reply:
            return reply

    provider = model = None
    for _ in range(MAX_STEPS):
        try:
            r = llm.chat(msgs, tools=TOOLS, max_tokens=1500)
        except llm.LLMError as e:
            return {"reply": f"O LLM não respondeu: {e}", "trace": trace, "actions": actions,
                    "ms": round((time.perf_counter() - t0) * 1000)}
        provider, model = r["provider"], r["model"]
        m = r["message"]
        calls = m.get("tool_calls") or _text_tool_calls(m.get("content") or "")
        if not calls:
            return {"reply": (m.get("content") or "").strip() or "(sem resposta)", "trace": trace, "actions": actions,
                    "provider": provider, "model": model, "ms": round((time.perf_counter() - t0) * 1000)}
        msgs.append({"role": "assistant", "content": "" if not m.get("tool_calls") else (m.get("content") or ""), "tool_calls": calls})
        for c in calls:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            try:
                res = _exec(name, args, actions)
            except SNAuthError:
                res = {"erro": "ServiceNow desconectado: peça ao Victor para clicar em Conectar."}
            except Exception as e:  # noqa: BLE001
                res = {"erro": f"{e.__class__.__name__}: {str(e)[:160]}"}
            trace.append({"tipo": "ferramenta", "nome": name, "args": args, "resultado": res})
            msgs.append({"role": "tool", "tool_call_id": c.get("id") or name, "content": json.dumps(res, ensure_ascii=False)[:6000]})
    return {"reply": "Parei depois de muitas etapas sem concluir. Reformule o pedido em partes menores.", "trace": trace,
            "actions": actions, "provider": provider, "model": model, "ms": round((time.perf_counter() - t0) * 1000)}

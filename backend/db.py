import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from backend.config import config

@contextmanager
def _conn():
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    """Inicializar banco com schema"""
    with _conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_number TEXT UNIQUE NOT NULL,
            sys_id TEXT,
            short_description TEXT,
            description TEXT,
            opened_at TEXT,
            caller_id TEXT,
            u_incident_location TEXT,
            localidade TEXT,
            localidade_confianca INTEGER,
            grupo TEXT,
            grupo_display TEXT,
            ritm_necessaria BOOLEAN,
            categoria TEXT,
            subcategory TEXT,
            pendencia TEXT,
            motivo TEXT,
            u_informal_service BOOLEAN DEFAULT 0,
            camera_codigo TEXT,
            status TEXT DEFAULT 'novo',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        cols = {r[1] for r in conn.execute("PRAGMA table_info(incidents)")}
        for name, ddl in (("opened_at", "TEXT"), ("caller_id", "TEXT"), ("u_incident_location", "TEXT"),
                          ("subcategory", "TEXT"), ("u_informal_service", "BOOLEAN DEFAULT 0"),
                          ("camera_codigo", "TEXT"), ("camera_lido_em", "TIMESTAMP"), ("cmdb_ci", "TEXT"),
                          ("pistas", "TEXT"), ("sn_estado", "TEXT"), ("sn_grupo", "TEXT"), ("nota_autor", "TEXT"),
                          ("saiu_em", "TIMESTAMP")):
            if name not in cols:
                conn.execute(f"ALTER TABLE incidents ADD COLUMN {name} {ddl}")
        # 'resolvido' (marcava 6/7/8 juntos; 8 = Aguardando Mudança) virou 'encerrado'; a reconciliação reclassifica
        conn.execute("UPDATE incidents SET status='encerrado' WHERE status='resolvido'")
        if "camera_lido_em" not in cols:
            # o leitor antigo gravava '' quando não achava a variável (id muda por formulário): reler esses
            conn.execute("UPDATE incidents SET camera_codigo=NULL WHERE camera_codigo='' AND status='analisado'")

        conn.execute("""CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_number TEXT,
            acao TEXT,
            resultado TEXT,
            chamou_claude BOOLEAN DEFAULT 0,
            tempo_ms FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        # retrato do backlog do ServiceNow, um por dia (horário de Brasília): tendência de entradas, saídas e idade
        conn.execute("""CREATE TABLE IF NOT EXISTS backlog_diario (
            dia TEXT PRIMARY KEY,
            total INTEGER, vencidos INTEGER, novos INTEGER, em_andamento INTEGER, idade_media_h REAL,
            numeros TEXT,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

def save_backlog_snapshot(dia: str, total: int, vencidos: int, novos: int, em_andamento: int, idade_media_h: float,
                          numeros: list[str]):
    """Upsert do retrato do dia (o último do dia vale)."""
    with _conn() as conn:
        conn.execute("""INSERT INTO backlog_diario (dia, total, vencidos, novos, em_andamento, idade_media_h, numeros)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(dia) DO UPDATE SET total=excluded.total, vencidos=excluded.vencidos,
                          novos=excluded.novos, em_andamento=excluded.em_andamento, idade_media_h=excluded.idade_media_h,
                          numeros=excluded.numeros, atualizado_em=CURRENT_TIMESTAMP""",
                     (dia, total, vencidos, novos, em_andamento, idade_media_h, ",".join(numeros)))

def list_backlog_snapshots(dias: int = 14) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM backlog_diario ORDER BY dia DESC LIMIT ?", (dias,)).fetchall()
    out = [dict(r) for r in rows][::-1]
    for r in out:
        r["numeros"] = [n for n in (r["numeros"] or "").split(",") if n]
    return out

def history_by_actions(acoes: tuple[str, ...], dias: int = 30) -> list[dict]:
    q = ",".join("?" * len(acoes))
    with _conn() as conn:
        rows = conn.execute(f"""SELECT incident_number, acao, resultado, chamou_claude, tempo_ms, created_at FROM history
                                WHERE acao IN ({q}) AND created_at >= datetime('now', ?) ORDER BY id""",
                            (*acoes, f"-{dias} days")).fetchall()
    return [dict(r) for r in rows]

def save_incident(incident_number: str, data: dict, status: str = "analisado"):
    """Inserir ou atualizar incidente (reprocessar não duplica)"""
    with _conn() as conn:
        conn.execute("""INSERT INTO incidents
            (incident_number, sys_id, short_description, description, opened_at, caller_id, u_incident_location, localidade,
             localidade_confianca, grupo, grupo_display, ritm_necessaria, categoria, subcategory,
             pendencia, motivo, u_informal_service, camera_codigo, cmdb_ci, pistas, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(incident_number) DO UPDATE SET
                sys_id=excluded.sys_id,
                opened_at=excluded.opened_at,
                caller_id=excluded.caller_id,
                u_incident_location=excluded.u_incident_location,
                short_description=excluded.short_description,
                description=excluded.description,
                localidade=excluded.localidade,
                localidade_confianca=excluded.localidade_confianca,
                grupo=excluded.grupo,
                grupo_display=excluded.grupo_display,
                ritm_necessaria=excluded.ritm_necessaria,
                categoria=excluded.categoria,
                subcategory=excluded.subcategory,
                pendencia=excluded.pendencia,
                motivo=excluded.motivo,
                u_informal_service=excluded.u_informal_service,
                camera_codigo=COALESCE(NULLIF(excluded.camera_codigo, ''), camera_codigo, excluded.camera_codigo),
                camera_lido_em=CASE WHEN excluded.camera_codigo IS NULL THEN camera_lido_em ELSE CURRENT_TIMESTAMP END,
                cmdb_ci=excluded.cmdb_ci,
                pistas=excluded.pistas,
                -- reanalisar nunca devolve à Entrada o que já saiu (despachado, tratado fora, encerrado)
                status=CASE WHEN incidents.status IN ('aprovado', 'tratado_fora', 'encerrado')
                            THEN incidents.status ELSE excluded.status END,
                updated_at=CURRENT_TIMESTAMP""",
            (incident_number, data.get("sys_id"), data.get("short_description"),
             data.get("description"), data.get("opened_at"), data.get("caller_id"),
             data.get("u_incident_location"), data.get("localidade"),
             data.get("localidade_confianca"), data.get("grupo"),
             data.get("grupo_display"), bool(data.get("ritm_necessaria")),
             data.get("categoria"), data.get("subcategory"), data.get("pendencia"), data.get("motivo"),
             bool(data.get("u_informal_service")), data.get("camera_codigo"), data.get("cmdb_ci"),
             json.dumps(data.get("pistas") or [], ensure_ascii=False), status))

def set_incident_status(incident_number: str, status: str, fields: dict | None = None):
    fields = {k: v for k, v in (fields or {}).items()
              if k in ("localidade", "grupo", "grupo_display", "ritm_necessaria")}
    sets = ", ".join(f"{k}=?" for k in fields)
    saiu = "saiu_em=CURRENT_TIMESTAMP, " if status in ("aprovado", "tratado_fora") else ""
    sql = (f"UPDATE incidents SET status=?, {sets + ', ' if sets else ''}{saiu}updated_at=CURRENT_TIMESTAMP "
           "WHERE incident_number=?")
    with _conn() as conn:
        conn.execute(sql, (status, *fields.values(), incident_number))

def _inc(row) -> dict:
    d = dict(row)
    try:
        d["pistas"] = json.loads(d.get("pistas") or "[]")
    except ValueError:
        d["pistas"] = []
    return d

def get_incident(incident_number: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM incidents WHERE incident_number=?",
                           (incident_number,)).fetchone()
    return _inc(row) if row else None

def set_fluxo(incident_number: str, status: str, sn_estado: str, sn_grupo: str, nota_autor: str | None):
    """Resultado da reconciliação com o ServiceNow (fluxo.reconciliar). Marca a hora em que saiu da Entrada."""
    with _conn() as conn:
        conn.execute("""UPDATE incidents SET
                          saiu_em=CASE WHEN status='analisado' AND ? <> 'analisado' THEN CURRENT_TIMESTAMP ELSE saiu_em END,
                          status=?, sn_estado=?, sn_grupo=?, nota_autor=?
                        WHERE incident_number=?""",
                     (status, status, sn_estado, sn_grupo, nota_autor, incident_number))

def incidents_para_reconciliar(dias: int = 3) -> list[dict]:
    """Entrada inteira + o que saiu nos últimos dias (pode ter sido encerrado/reaberto no ServiceNow)."""
    with _conn() as conn:
        rows = conn.execute("""SELECT incident_number, sys_id, status FROM incidents
                               WHERE status='analisado'
                                  OR (status IN ('aprovado', 'tratado_fora', 'encerrado')
                                      AND COALESCE(saiu_em, updated_at) >= datetime('now', ?))""",
                            (f"-{dias} days",)).fetchall()
    return [dict(r) for r in rows]

def list_saida(horas: int = 24, limit: int = 200) -> list[dict]:
    """Saída: despachados pelo agente e tratados fora dele nas últimas `horas` (mais recentes primeiro)."""
    with _conn() as conn:
        rows = conn.execute("""SELECT * FROM incidents WHERE status IN ('aprovado', 'tratado_fora')
                                 AND COALESCE(saiu_em, updated_at) >= datetime('now', ?)
                               ORDER BY COALESCE(saiu_em, updated_at) DESC LIMIT ?""",
                            (f"-{horas} hours", limit)).fetchall()
    return [_inc(r) for r in rows]

def list_incidents(limit: int = 50, only_pending: bool = True) -> list[dict]:
    """Listar incidentes. only_pending=True: só a Entrada (status 'analisado')."""
    with _conn() as conn:
        if only_pending:
            rows = conn.execute("""SELECT * FROM incidents
                                   WHERE status = 'analisado'
                                   ORDER BY updated_at DESC, id DESC LIMIT ?""",
                                (limit,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM incidents ORDER BY updated_at DESC, id DESC LIMIT ?",
                                (limit,)).fetchall()
    return [_inc(r) for r in rows]

def add_history(incident_number: str, acao: str, resultado: str = "",
                chamou_claude: bool = False, tempo_ms: float = 0.0):
    with _conn() as conn:
        conn.execute("""INSERT INTO history (incident_number, acao, resultado, chamou_claude, tempo_ms)
            VALUES (?, ?, ?, ?, ?)""",
            (incident_number, acao, resultado, int(chamou_claude), tempo_ms))

def list_history(limit: int = 100, incident_number: str | None = None,
                 acao: str | None = None) -> list[dict]:
    where, params = [], []
    if incident_number:
        where.append("incident_number = ?"); params.append(incident_number)
    if acao:
        where.append("acao = ?"); params.append(acao)
    sql = "SELECT * FROM history"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    with _conn() as conn:
        rows = conn.execute(sql, (*params, limit)).fetchall()
    return [dict(r) for r in rows]

def get_rules():
    """Carregar regras"""
    with open(config.RULES_PATH, encoding="utf-8") as f:
        return json.load(f)

def save_rules(rules: dict):
    with open(config.RULES_PATH, "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)

def get_metrics():
    """Calcular métricas a partir do histórico"""
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]

        analises, sem_claude, tempo_medio = conn.execute(
            """SELECT COUNT(*),
                      COALESCE(SUM(CASE WHEN chamou_claude = 0 THEN 1 ELSE 0 END), 0),
                      COALESCE(AVG(tempo_ms), 0)
               FROM history WHERE acao = 'analise'""").fetchone()

        chamadas_hoje = conn.execute(
            """SELECT COUNT(*) FROM history
               WHERE chamou_claude = 1 AND DATE(created_at, '-3 hours') = DATE('now', '-3 hours')""").fetchone()[0]

        aprovados, editados = conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN acao='aprovado' THEN 1 ELSE 0 END), 0),
                      COALESCE(SUM(CASE WHEN acao='editado' THEN 1 ELSE 0 END), 0)
               FROM history""").fetchone()

    with _conn() as conn:
        pendentes = conn.execute(
            "SELECT COUNT(*) FROM incidents WHERE status = 'analisado'").fetchone()[0]

    decididos = aprovados + editados
    return {
        "total_processados": total,
        "pendentes": pendentes,
        "automacao_percentual": round(sem_claude / analises * 100, 1) if analises else 0.0,
        "tempo_medio_segundos": round(tempo_medio / 1000, 2),
        "chamadas_claude_hoje": chamadas_hoje,
        # % de sugestões aprovadas sem edição manual
        "precisao_percentual": round(aprovados / decididos * 100, 1) if decididos else 0.0,
    }

def get_breakdown() -> dict:
    """Distribuições para o painel de métricas"""
    with _conn() as conn:
        por_localidade = [dict(r) for r in conn.execute(
            """SELECT COALESCE(localidade, 'Sem destino') AS localidade, COUNT(*) AS total
               FROM incidents GROUP BY 1 ORDER BY total DESC""")]
        por_status = [dict(r) for r in conn.execute(
            "SELECT status, COUNT(*) AS total FROM incidents GROUP BY status ORDER BY total DESC")]
        por_origem = [dict(r) for r in conn.execute(
            """SELECT CASE WHEN chamou_claude = 1 THEN 'Regras + LLM' ELSE 'Regras locais' END AS origem,
                      COUNT(*) AS total
               FROM history WHERE acao = 'analise' GROUP BY 1""")]
    return {"por_localidade": por_localidade, "por_status": por_status, "por_origem": por_origem}

import re
from collections import Counter
from datetime import datetime, timedelta

TEMAS = {
    "Elétrica": r"energia|el[eé]tric|no-?break|nobreak|ups\b|disjuntor|queda de luz|sem luz|power",
    "Rede / link": r"\bredes?\b|link|switch|fibra|rompid|ping|conectividade|vpn",
    "Câmera": r"c[aâ]mera|camera|imagem|visualiza|lente|ptz",
    "Gravação (NVR/DVR)": r"nvr|dvr|grava[cç]|storage|hd\b|disco",
    "Servidor / software": r"servidor|scom|heartbeat|digifort|servi[cç]o|windows|licen",
    "LORA / tag": r"lora|tag\b",
}


def _norm_title(t: str) -> str:
    t = re.sub(r"^\[[^\]]*\]\s*-?\s*", "", (t or "").lower())
    t = re.sub(r"\b[a-z]{2,4}-[a-z]{2,4}-[a-z]+\d*\b|\d+", "#", t)
    return re.sub(r"\s+", " ", t).strip(" -#")[:70]


def get_insights() -> dict:
    """Padrões para o analista: informais, recorrência, temas (elétrica etc.) por unidade e sinais de anomalia."""
    with _conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT incident_number, short_description, description, localidade, opened_at, created_at, "
            "u_informal_service, localidade_confianca, grupo, camera_codigo FROM incidents")]

    unidade = lambda r: r["localidade"] or "Sem destino"
    total = len(rows)

    informais = Counter(unidade(r) for r in rows if r["u_informal_service"])
    por_unidade = Counter(unidade(r) for r in rows)

    temas = {}
    for tema, rx in TEMAS.items():
        por = Counter(unidade(r) for r in rows
                      if re.search(rx, f"{r['short_description']} {r['description']}", re.IGNORECASE))
        if por:
            temas[tema] = {"total": sum(por.values()),
                           "por_unidade": [{"localidade": k, "total": v} for k, v in por.most_common(5)]}

    rec = {}
    for r in rows:
        k = _norm_title(r["short_description"])
        if k:
            rec.setdefault(k, []).append(r)
    recorrentes = sorted(
        ({"padrao": k, "total": len(v), "unidades": sorted({unidade(x) for x in v}),
          "incidentes": [x["incident_number"] for x in v][:6]} for k, v in rec.items() if len(v) >= 2),
        key=lambda x: -x["total"])[:10]

    cams = {}
    for r in rows:
        if r["camera_codigo"]:
            cams.setdefault(r["camera_codigo"], []).append(r)
    cameras = sorted(({"camera": k, "total": len(v), "localidade": unidade(v[0]), "incidentes": [x["incident_number"] for x in v][:6]}
                      for k, v in cams.items() if len(v) >= 2), key=lambda x: -x["total"])[:10]

    # sinais de atenção: rajada numa unidade (>=3 abertos em 24h) e unidade com >=40% informais
    alertas, limite = [], datetime.utcnow() - timedelta(hours=24)
    recentes = Counter()
    for r in rows:
        try:
            if datetime.fromisoformat((r["opened_at"] or "").replace("Z", "")) >= limite:
                recentes[unidade(r)] += 1
        except ValueError:
            pass
    for u, n in recentes.items():
        if n >= 3:
            alertas.append({"tipo": "rajada", "localidade": u, "texto": f"{n} incidentes abertos nas últimas 24h em {u}"})
    for u, n in informais.items():
        if por_unidade[u] >= 3 and n / por_unidade[u] >= 0.4:
            alertas.append({"tipo": "informal", "localidade": u,
                            "texto": f"{n} de {por_unidade[u]} incidentes em {u} são atendimento informal"})
    for c in cameras:
        alertas.append({"tipo": "camera", "localidade": c["localidade"],
                        "texto": f"Câmera {c['camera']} com {c['total']} incidentes abertos ({c['localidade']})"})
    for r in rows:
        if not r["grupo"]:
            alertas.append({"tipo": "sem_destino", "localidade": None,
                            "texto": f"{r['incident_number']} sem localidade definida"})

    return {
        "total": total,
        "informais_por_localidade": [{"localidade": k, "total": v, "de": por_unidade[k]} for k, v in informais.most_common(10)],
        "total_informais": sum(informais.values()),
        "temas": temas,
        "recorrentes": recorrentes,
        "cameras_recorrentes": cameras,
        "com_camera": len(cams),
        "alertas": alertas[:12],
    }


def update_routing(incident_number: str, res: dict):
    """Atualiza só o destino sugerido (localidade/grupo/confiança/motivo) de um incidente ainda pendente."""
    with _conn() as conn:
        conn.execute("""UPDATE incidents SET localidade=?, localidade_confianca=?, grupo=?, grupo_display=?,
                        ritm_necessaria=?, motivo=?, updated_at=CURRENT_TIMESTAMP
                        WHERE incident_number=? AND status='analisado'""",
                     (res.get("localidade"), res.get("localidade_confianca"), res.get("grupo"),
                      res.get("grupo_display"), bool(res.get("ritm_necessaria")), res.get("motivo"),
                      incident_number))


def incidents_sem_camera(limit: int = 8) -> list[dict]:
    """Pendentes sem código da câmera: nunca lido (leitura falhou) ou lido vazio há mais de 30 min
    (o solicitante/técnico pode preencher o campo depois)."""
    with _conn() as conn:
        rows = conn.execute("""SELECT incident_number, sys_id, short_description, description FROM incidents
                               WHERE status='analisado' AND sys_id IS NOT NULL
                                 AND (camera_codigo IS NULL OR (camera_codigo='' AND
                                      (camera_lido_em IS NULL OR camera_lido_em < datetime('now', '-30 minutes'))))
                               ORDER BY camera_lido_em IS NOT NULL, id DESC LIMIT ?""", (limit,)).fetchall()
    return [dict(r) for r in rows]


def set_camera(incident_number: str, codigo: str):
    with _conn() as conn:
        conn.execute("UPDATE incidents SET camera_codigo=?, camera_lido_em=CURRENT_TIMESTAMP WHERE incident_number=?",
                     (codigo, incident_number))

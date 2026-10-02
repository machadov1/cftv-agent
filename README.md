# CFTV Agent — Sistema de Automação de Incidentes

Automação inteligente de incidentes CFTV no ServiceNow (ArcelorMittal) com **regras determinísticas** + LLM em edge cases.

**Economia:** ~200–300 tokens/dia (vs. 5k–10k via chat) | **Acurácia:** 80–90% das análises sem IA

---

## ✨ Funcionalidades

### 🎯 Classificação Automática
- **25+ regras** com reconhecimento de localidade por texto, IC e dicas contextuais
- **Pistas fora do texto**: servidor (IC), localização do IC, local do solicitante → resolve ambiguidades
- **LLM sob demanda**: chamado apenas em ~10–20% dos casos (confiança < 70%)

### 📊 Dashboard Web Local
- **Fila com 3 abas**: Entrada (novo), Sem destino (sem grupo), Saída · 24h (despachado)
- **Detalhe rico**: payload completo, pistas, histórico, status ServiceNow
- **Validação SCOM**: ping automático com print anexado (heartbeat, banda, disco)
- **Evidência de câmera**: snapshot Digifort com timestamp
- **E-mail A4** via `mailto:` (Outlook padrão, não bloqueia servidor)
- **Regras editáveis** em tempo real, com regex validada
- **Métricas**: % automação, mediana até despacho, precisão, KPIs por unidade

### 🔧 Automação ServiceNow
- **PATCH único** com localidade, grupo, categoria, subcategoria, work note
- **RITM de acompanhamento** (PEMT, infraestrutura, elétrica, etc) com 20 dias de monitoramento
- **Encerramento** (fluxo 9.3): Resolvido + close_code Solved + nota + work note
- **Teams/Slack**: rascunhos editáveis (sem envio automático)
- **Histórico local**: quem fez o quê, quando

### 🎓 Aprendizado de Regras
- Código de câmera (`BM-001`, `PIR-005`) aprendido do texto/formulário
- Prefixo consistente (≥2 incidentes, ≥80%) → sugere nova regra
- Aceitação atualiza regras e reavalia incidentes sem localidade

---

## 🚀 Quick Start

### Pré-requisitos
- **Python 3.10+** | **Node 18+** | **Git**
- Credenciais ServiceNow (`SERVICENOW_TOKEN`)
- Opcional: LLM local (OpenRouter ou Anthropic API)

### Setup (5 min)

```bash
# 1. Clone
git clone https://github.com/machadov1/cftv-agent.git
cd cftv-agent

# 2. Backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python scripts/setup_db.py

# 3. Frontend
cd dashboard && npm install && cd ..

# 4. Config
cp .env.example .env
# Editar .env com suas credenciais ServiceNow
```

### Rodar

**Modo desenvolvimento:**
```bash
# Terminal 1: Backend
source venv/bin/activate
python -m uvicorn backend.main:app --reload

# Terminal 2: Frontend
cd dashboard && npm run dev
```

**Modo produção:**
```bash
./iniciar.cmd  # Windows (sobe API + painel em http://127.0.0.1:8000)
```

---

## 📁 Arquitetura

```
backend/
├── main.py              # FastAPI + health check
├── rules_engine.py      # Regras determinísticas + pistas
├── servicenow_api.py    # Integração (leitura + PATCH)
├── db.py                # SQLite (incidentes, histórico, regras)
├── fluxo.py             # Entrada/Saída + reconciliação
├── pistas.py            # IC, localização, solicitante
├── a4.py                # E-mail A4 (UWB/automação)
├── scom.py              # Validação SCOM (ping automático)
├── digifort.py          # Snapshot Digifort
└── routes/              # API endpoints

dashboard/
├── src/
│   ├── App.jsx          # Layout principal (nav, abas)
│   ├── pages/           # Incidents, Rules, History, Metrics, Tasks, Camera, Agent
│   ├── components/      # Detail, Camera panel, RITM, Hold button
│   └── api.js           # Fetch wrapper
└── vite.config.js       # Build fast

data/
├── cftv.db              # SQLite (auto-criado)
├── rules.json           # Regras (25+)
├── mapeamentos.json     # Localidades, ICs, filas
├── a4_queues.json       # Template e-mail A4
└── filas.json           # Classificação de filas
```

---

## 🧪 Testes

```bash
pytest tests/ -v           # Todos (129 testes)
pytest tests/test_fluxo.py # Entrada/Saída
pytest tests/test_a4_email.py  # E-mail A4
```

Testes **nunca** chamam LLM real ou ServiceNow (stubs em `conftest.py`).

---

## 📊 Fluxo de um Incidente

```
Usuário cola INC no dashboard
           ↓
Backend busca no ServiceNow
           ↓
apply_rules() → localidade, grupo, RITM?
           ├─ Texto matches regra? → confidente
           ├─ IC/localização dá pista? → boa confiança
           └─ Ambíguo? LLM decide (raro)
           ↓
Dashboard mostra sugestão:
┌─────────────────────────────────┐
│ INC3997102                      │
│ Piracicaba (100%) → AMS-TI-CFTV-PIR │
│ [Pistas] [Payload] [Despachar]  │
└─────────────────────────────────┘
           ↓
Usuário clica "Aprovar" (segurar 0.45s)
           ↓
PATCH ServiceNow → estado, grupo, título, work note
INSERT histórico
           ↓
✓ Processado em 0.8s
```

---

## 🎨 Visual

**Design:** "Mesa de Despacho" (Swiss industrial)
- **Tipografia:** Bahnschrift (Windows), Consolas (monospace)
- **Tema escuro:** Fundo `#1f2226` (grafite, não preto), traço cinza médio
- **Tokens:** Por estado (vermelho=bloqueio, verde=despacho, âmbar=teste, cobalto=ação)
- **Segurança no gesto:** Despachar = segurar 0.45s; lotes com Shift/Ctrl

---

## 📈 Métricas

**Dashboard → Aba Métricas**

| Métrica | Descrição |
|---------|-----------|
| **Automação %** | Casos resolvidos sem LLM |
| **Mediana (s)** | Tempo entre entrada e despacho |
| **Precisão** | Acertos sem edição pós-despacho |
| **SLA** | Vencidos/próximos por equipe |
| **Câmeras crônicas** | Padrões (bandas, offline) |
| **Backlog** | Tendência 3+ dias |

---

## 🔑 Variáveis de Ambiente

```bash
# LLM (OpenRouter > Anthropic)
OPENROUTER_API_KEY=sk-or-...
# ANTHROPIC_API_KEY=sk-...

# ServiceNow
SERVICENOW_INSTANCE=amamericas
SERVICENOW_TOKEN=xyzabc...
SERVICENOW_DRY_RUN=true  # false = escrita real

# App
APP_ENV=development
DEBUG=True
```

---

## 📚 Documentação

- **[CLAUDE.md](./CLAUDE.md)** — Contexto completo do projeto
- **[IMPLEMENTACAO.md](./IMPLEMENTACAO.md)** — Setup detalhado, troubleshooting
- **Digifort API** → `API-DIGIFORT/` (PDFs inclusos)

---

## 🤝 Contribuições

- Fork ou abra uma issue
- Teste com `pytest` antes de PR
- Mantenha cobertura ≥80%

---

## 📜 Licença

Privado (ArcelorMittal / Grupo Alert). Não distribuir sem autorização.

---

## 📞 Contato

**Victor Alexandre Basilio Machado**  
Network Analyst @ A4 Solutions / Grupo Alert  
vic.machado@arcelormittal.com.br

**Versão:** 0.2 (02/10/2026)  
**Status:** Produção (dry-run habilitado por padrão)

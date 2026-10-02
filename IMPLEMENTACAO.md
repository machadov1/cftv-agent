# CFTV Agent — Guia de Implementação

## Visão Geral

Sistema local de automação para gerenciamento de incidentes CFTV no ServiceNow. Agent Python + Dashboard React rodando localhost com integração mínima a Claude API (apenas edge cases).

**Stack:**
- Backend: Python 3.10+ (FastAPI)
- Frontend: React 18 + TailwindCSS
- Database: SQLite (local, zero setup)
- Agent: Python + Anthropic SDK

**Custo de tokens:** ~200-300/dia (vs. 5k-10k via chat)

---

## 1. Pré-requisitos

### 1.1 Na sua máquina (Windows)

```powershell
# Verificar versões
python --version        # Python 3.10+ obrigatório
node --version          # Node 18+ para React
npm --version           # Vem com Node

# Se não tiver:
# Python: https://www.python.org/downloads/
# Node: https://nodejs.org/
```

### 1.2 Chaves e credenciais

```
ANTHROPIC_API_KEY=sk-...          # Sua chave Claude API
SERVICENOW_USER=seu_user          # ServiceNow user (optional, se usar SSO no browser)
SERVICENOW_PASSWORD=seu_pass      # (optional)
SERVICENOW_INSTANCE=amamericas   # Sempre amamericas.service-now.com
```

Salvar em `.env` na raiz do projeto (será ignorado pelo git).

---

## 2. Setup Inicial (30 min)

### 2.1 Clonar/criar estrutura

```bash
# Crie a pasta do projeto
mkdir ~/cftv-agent
cd ~/cftv-agent

# Estrutura será criada por Claude Code (ver claude.md)
```

### 2.2 Backend

```bash
# Criar venv Python
python -m venv venv

# Ativar (Windows)
venv\Scripts\activate

# Instalar dependências
pip install fastapi uvicorn python-dotenv sqlite3 anthropic requests
```

### 2.3 Frontend

```bash
# Criar React app
npx create-react-app dashboard

cd dashboard
npm install axios recharts tailwindcss

# Config TailwindCSS (automático com create-react-app)
npx tailwindcss init -p

cd ..
```

### 2.4 Estrutura de arquivos

Depois de 2.2 e 2.3, você terá:

```
cftv-agent/
├── .env                           # ← Cria manualmente com chaves
├── .gitignore                     # ← Git ignore (db, venv, node_modules)
├── claude.md                      # ← Claude context (pronto abaixo)
├── IMPLEMENTACAO.md              # ← Este arquivo
├── requirements.txt              # ← pip freeze
│
├── backend/
│   ├── main.py                   # FastAPI app
│   ├── rules_engine.py           # Lógica determinística
│   ├── claude_caller.py          # Chama API (raro)
│   ├── servicenow_api.py         # Integração SN
│   ├── db.py                     # SQLite queries
│   ├── models.py                 # Pydantic schemas
│   └── config.py                 # Env vars
│
├── data/
│   ├── cftv.db                   # ← SQLite (criado na 1ª execução)
│   ├── rules.json                # ← Rules default (ver 5.1)
│   └── mapeamentos.json          # ← Localidades, grupos, sys_ids
│
├── dashboard/
│   ├── public/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── pages/
│   │   │   ├── IncidentsPage.jsx
│   │   │   ├── RulesEditor.jsx
│   │   │   ├── HistoryPage.jsx
│   │   │   └── MetricsPage.jsx
│   │   ├── components/
│   │   │   ├── IncidentCard.jsx
│   │   │   └── RuleForm.jsx
│   │   ├── api.js                # Chamadas ao backend
│   │   └── styles/
│   │       └── tailwind.css
│   └── package.json
│
└── scripts/
    ├── setup_db.py               # Init banco com dados da skill
    └── sync_rules.py             # Sincroniza regras
```

---

## 3. Inicialização do Banco

### 3.1 Script `setup_db.py`

```python
# cftv-agent/scripts/setup_db.py
import sqlite3
import json

def init_db():
    conn = sqlite3.connect("../data/cftv.db")
    c = conn.cursor()
    
    # Tabela de incidentes
    c.execute("""CREATE TABLE IF NOT EXISTS incidents (
        id INTEGER PRIMARY KEY,
        incident_number TEXT UNIQUE,
        short_description TEXT,
        localidade TEXT,
        grupo TEXT,
        ritm_necessaria BOOLEAN,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Tabela de regras
    c.execute("""CREATE TABLE IF NOT EXISTS rules (
        id INTEGER PRIMARY KEY,
        pattern TEXT,
        localidade TEXT,
        grupo TEXT,
        ritm BOOLEAN,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Inserir regras padrão
    regras_padrao = [
        ("PIR", "Piracicaba", "AMS-TI-CFTV-PIR", True),
        ("MDE", "João Monlevade", "AMS-TI-CFTV-MDE", True),
        # ... (ver seção 5.1)
    ]
    
    for pattern, loc, grupo, ritm in regras_padrao:
        c.execute("INSERT OR IGNORE INTO rules (pattern, localidade, grupo, ritm) VALUES (?, ?, ?, ?)",
                  (pattern, loc, grupo, ritm))
    
    conn.commit()
    conn.close()
    print("✓ Database initialized")

if __name__ == "__main__":
    init_db()
```

Executar uma vez:
```bash
cd scripts
python setup_db.py
```

---

## 4. Rodando o projeto

### 4.1 Terminal 1 — Backend

```bash
cd cftv-agent
source venv/bin/activate  # ou venv\Scripts\activate (Windows)
python backend/main.py
```

Esperado:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### 4.2 Terminal 2 — Frontend

```bash
cd cftv-agent/dashboard
npm start
```

Esperado:
```
Compiled successfully!
You can now view dashboard in the browser.
Local: http://localhost:3000
```

### 4.3 Acessar

Abra `http://localhost:3000` no navegador.

---

## 5. Configuração de Regras

### 5.1 `data/rules.json` (padrão)

```json
{
  "rules": [
    {
      "id": 1,
      "pattern": "PIR",
      "localidade": "Piracicaba",
      "grupo": "287a11d0dbd9b7c0e5f36451ca961955",
      "ritm_necessaria": false,
      "categoria": "network",
      "subcategory": "Telecom"
    },
    {
      "id": 2,
      "pattern": "MDE|Monlevade",
      "localidade": "João Monlevade",
      "grupo": "e07a11d0dbd9b7c0e5f36451ca96194e",
      "ritm_necessaria": true,
      "categoria": "network"
    },
    {
      "id": 3,
      "pattern": "fibra.*rompida|rompida.*fibra",
      "localidade": null,
      "ritm_necessaria": true,
      "pendencia": "Infraestrutura"
    }
  ]
}
```

Editar via Dashboard "Rules Editor" (aba Regras).

---

## 6. Chamadas à Claude API

### 6.1 Quando chamar (raro)

```python
# backend/claude_caller.py

from anthropic import Anthropic

client = Anthropic()

def call_claude_for_localidade(description: str) -> str:
    """Identifica localidade quando não há match nas regras."""
    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        messages=[
            {
                "role": "user",
                "content": f"""Identifique a localidade dessa descrição de incidente.
                Responda com APENAS o nome da cidade ou 'desconhecida'.
                
                Descrição: {description}
                
                Opções válidas: Piracicaba, João Monlevade, Resende, Juiz de Fora, Bauru, Barra Mansa, Sabará."""
            }
        ]
    )
    return message.content[0].text.strip()

def call_claude_for_ritm(description: str, localidade: str) -> bool:
    """Decide se precisa RITM quando há dúvida."""
    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=50,
        messages=[
            {
                "role": "user",
                "content": f"""Incidente: {description}
                Localidade: {localidade}
                
                Precisa de RITM (requisição de infraestrutura/rede/pemt)? Responda: SIM ou NÃO."""
            }
        ]
    )
    return "SIM" in message.content[0].text.upper()
```

**Custo:** 1 chamada = ~50-100 tokens. Com 5-10 chamadas/dia = 200-300 tokens (aceitável).

---

## 7. Integração ServiceNow

### 7.1 `backend/servicenow_api.py`

```python
import requests
from dotenv import load_dotenv
import os

load_dotenv()

class ServiceNowAPI:
    def __init__(self):
        self.base_url = f"https://{os.getenv('SERVICENOW_INSTANCE')}.service-now.com"
        self.token = os.getenv('SERVICENOW_TOKEN')  # Token gerado no SN
    
    def get_incident(self, incident_number: str):
        url = f"{self.base_url}/api/now/table/incident"
        params = {
            'sysparm_query': f'number={incident_number}',
            'sysparm_fields': 'sys_id,number,short_description,description,state,assignment_group,cmdb_ci'
        }
        headers = {
            'X-UserToken': self.token,
            'Accept': 'application/json'
        }
        response = requests.get(url, params=params, headers=headers)
        return response.json()['result'][0] if response.json()['result'] else None
    
    def patch_incident(self, sys_id: str, fields: dict):
        url = f"{self.base_url}/api/now/table/incident/{sys_id}"
        headers = {
            'X-UserToken': self.token,
            'Content-Type': 'application/json'
        }
        response = requests.patch(url, json=fields, headers=headers)
        return response.status_code == 200
```

**Token ServiceNow:** Gerar em Admin → API tokens ou usar o `window.g_ck` do portal.

---

## 8. Deploy (opcional)

### 8.1 Docker Compose (rodar tudo junto)

```yaml
# docker-compose.yml
version: '3.8'

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "8000:8000"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - ./data:/app/data
    command: python backend/main.py

  frontend:
    build:
      context: ./dashboard
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    depends_on:
      - backend
```

Rodar:
```bash
docker-compose up
```

### 8.2 Systemd (Linux/WSL)

Se rodar em um servidor:

```ini
# /etc/systemd/system/cftv-agent.service
[Unit]
Description=CFTV Agent
After=network.target

[Service]
Type=simple
User=victor
WorkingDirectory=/home/victor/cftv-agent
ExecStart=/home/victor/cftv-agent/venv/bin/python backend/main.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable cftv-agent
sudo systemctl start cftv-agent
```

---

## 9. Troubleshooting

| Erro | Solução |
|---|---|
| `ModuleNotFoundError: No module named 'fastapi'` | `pip install -r requirements.txt` |
| `Port 8000 already in use` | `lsof -i :8000` (Mac/Linux) ou `netstat -ano \| findstr :8000` (Windows). Kill o processo ou mude porta em `.env` |
| `CORS error no dashboard` | Adicionar CORS no FastAPI: `from fastapi.middleware.cors import CORSMiddleware` |
| `SQLite database is locked` | Fechar outras conexões. SQLite é single-writer. Usar PostgreSQL se escalando |
| `ANTHROPIC_API_KEY not found` | Verificar `.env` na raiz do projeto (não em subpastas) |

---

## 10. Próximas fases (roadmap)

**Fase 2 (Semana 2):**
- Webhook do ServiceNow → auto-import de incidentes
- Auto-execution (processa de madrugada, você aprova de manhã)

**Fase 3 (Semana 3):**
- Integração RITM automática (abre sem passar por você)
- Notificação Teams automática

**Fase 4 (Semana 4):**
- ML leve (aprende quais regras você corrige)
- Dashboard de métricas avançadas

---

## 11. Referências rápidas

**Rodar tudo:**
```bash
# Terminal 1
source venv/bin/activate && python backend/main.py

# Terminal 2
cd dashboard && npm start
```

**Resetar banco:**
```bash
rm data/cftv.db
python scripts/setup_db.py
```

**Ver logs:**
```bash
# Backend está em stdout (terminal 1)
# Frontend: DevTools (F12) → Console
```

**Gerar requirements.txt:**
```bash
pip freeze > requirements.txt
```

---

**Dúvidas?** Ver `claude.md` para contexto completo, ou avisar Victor para ajustar.

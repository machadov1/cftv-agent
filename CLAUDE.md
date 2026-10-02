# CFTV Agent — Contexto do Projeto

## 📋 Visão Geral

**Nome:** CFTV Agent Local  
**Descrição:** Sistema de automação para incidentes CFTV no ServiceNow (Grupo Alert / ArcelorMittal) com Dashboard web local e Agent Python inteligente.  
**Owner:** Victor Alexandre Basilio Machado  
**Stack:** Python (FastAPI) + React + SQLite  
**Custo:** ~200-300 tokens Claude/dia

---

## 🎯 Objetivo

Substituir processamento manual de incidentes via Claude chat por um **agent local determinístico** que:

1. Aplica regras locais (80-90% dos casos)
2. Chama Claude API apenas em edge cases (~10-20%)
3. Fornece dashboard para review, ajuste de regras e métricas
4. Executa automação no ServiceNow (PATCH, RITM, work notes)

**Economia:** De 5k-10k tokens/dia (chat) → 200-300 tokens/dia (API)

---

## 📁 Estrutura de Arquivos

```
cftv-agent/
├── IMPLEMENTACAO.md              # Guia de setup (ler primeiro)
├── claude.md                     # Este arquivo
├── .env                          # Env vars (NÃO committar)
├── requirements.txt              # pip freeze
├── .gitignore
│
├── backend/
│   ├── main.py                   # FastAPI app (uvicorn main:app --reload)
│   ├── config.py                 # Carrega .env
│   ├── models.py                 # Pydantic schemas
│   ├── db.py                     # SQLite CRUD (init_db, save_incident, get_rules)
│   ├── rules_engine.py           # Lógica determinística (apply_rules)
│   ├── claude_caller.py          # Chama API (call_claude_for_localidade, call_claude_for_ritm)
│   ├── servicenow_api.py         # Integração SN (get_incident, patch_incident)
│   ├── routes/
│   │   ├── incidents.py          # POST /incidents, GET /incidents/{id}
│   │   ├── rules.py              # GET /rules, POST /rules, PUT /rules/{id}
│   │   ├── history.py            # GET /history
│   │   └── metrics.py            # GET /metrics
│   └── utils.py                  # Helpers
│
├── dashboard/
│   ├── public/
│   ├── src/
│   │   ├── App.jsx               # Layout principal (nav, pages)
│   │   ├── index.css             # Tailwind globals
│   │   ├── pages/
│   │   │   ├── IncidentsPage.jsx # Processar/listar incidentes
│   │   │   ├── RulesPage.jsx     # Editor de regras
│   │   │   ├── HistoryPage.jsx   # Histórico com filtros
│   │   │   └── MetricsPage.jsx   # Charts: automação %, tempo médio, etc.
│   │   ├── components/
│   │   │   ├── IncidentCard.jsx  # Card com sugestão + aprovação
│   │   │   ├── RuleForm.jsx      # Form para criar/editar regras
│   │   │   ├── Header.jsx        # Nav, logo, hora
│   │   │   └── LoadingSpinner.jsx
│   │   ├── api.js                # fetch wrapper para backend
│   │   ├── hooks/
│   │   │   └── useMetrics.js     # Custom hook para métricas
│   │   └── styles/
│   │       └── tailwind.css
│   ├── tailwind.config.js        # Config TW
│   └── package.json
│
├── data/
│   ├── cftv.db                   # SQLite (criado na 1ª execução)
│   ├── rules.json                # Rules padrão (seed)
│   └── mapeamentos.json          # Localidades, grupos, sys_ids (importado da skill)
│
├── scripts/
│   ├── setup_db.py               # Init banco com dados padrão
│   └── snapshot_dashboard.py     # Captura (só leitura) de um board do ServiceNow
│
└── iniciar.cmd                   # Sobe a API + painel e abre o navegador
```
Arquivos legados (scaffold, scripts avulsos, node_modules da raiz) foram movidos para `C:\PROJETOS\cftv-agent-arquivo\` em 30/09/2026.

---

## 🔧 Stack & Dependências

### Backend (Python 3.10+)
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-dotenv==1.0.0
requests
pydantic
```
(LLM chamado via HTTP com `requests` — OpenRouter ou API Anthropic; sem SDK. Versões em `requirements.txt`.)

Instalar: `pip install -r requirements.txt`

### Frontend (Node 18+)
```
react@18 + react-dom
vite (+ @vitejs/plugin-react)
recharts
tailwindcss v4 (+ @tailwindcss/vite)
```
(Vite, não create-react-app. Variável de ambiente do front: `VITE_API_URL`.)

Instalar: `npm install` (dentro de `dashboard/`)

### Banco
```
SQLite (built-in, zero setup)
```

---

## 🚀 Como Rodar

### Setup (1ª vez)
```bash
# 1. Copiar .env.example para .env e preencher:
OPENROUTER_API_KEY=sk-or-...   # (ou ANTHROPIC_API_KEY como fallback)
SERVICENOW_INSTANCE=amamericas
SERVICENOW_TOKEN=...
SERVICENOW_DRY_RUN=true        # true = Aprovar não escreve no ServiceNow

# 2. Backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python scripts/setup_db.py

# 3. Frontend
cd dashboard
npm install
cd ..
```

### Uso diário
`iniciar.cmd` (duplo clique): sobe `backend/main.py`, espera o `/health` e abre **http://127.0.0.1:8000**.
O backend serve o build do painel (`dashboard/dist`) na mesma porta; mudou o front, rode `npm run build` em `dashboard/`.
O `api.js` usa a mesma origem no build. Nunca fixar `http://localhost:8000`: outra origem cai no CORS e `localhost`
pode resolver para `::1` ("Failed to fetch" em tudo).

### Dev do front (opcional)
`cd dashboard && npm run dev` → http://localhost:3000, falando com a API em `http://127.0.0.1:8000`.

### Endpoints principais
- `POST /incidents` — Processar incidente (`{"incident_number": "INC..."}`): busca no SN, aplica regras, LLM só se confiança < 70
- `POST /incidents/{inc}/approve` — Aplica sugestão (ou overrides) no ServiceNow (respeita `SERVICENOW_DRY_RUN`)
- `GET /incidents`, `GET /incidents/{inc}` — Incidentes analisados
- `GET /rules`, `POST /rules`, `PUT /rules/{id}`, `DELETE /rules/{id}` — CRUD de regras (regex validada)
- `GET /history?acao=&incident_number=` — Histórico (analise / aprovado / editado)
- `GET /metrics` — Métricas (% automação, tempo médio, precisão)
- `GET /health` — Status (LLM habilitado? dry-run?)

Testes: `venv\Scripts\python.exe -m pytest tests`

---

## 📊 Fluxo de um Incidente

```
Usuario cola INC na Dashboard
        ↓
Backend: GET /incidents (parsing + read do SN)
        ↓
rules_engine.apply_rules (determinístico)
        ├─ Extrai localidade
        ├─ Busca grupo no mapeamento
        ├─ Decide se RITM
        └─ Se confiança < 70% → chama Claude API (raro)
        ↓
Dashboard mostra sugestão:
┌────────────────────────────────┐
│ INC: INC3997102                │
│ Localidade: Piracicaba (100%)   │
│ Grupo: AMS-TI-CFTV-PIR         │
│ RITM: SIM (por quê: offline)    │
│ [Chamar Claude] [Aprovar] [Editar] │
└────────────────────────────────┘
        ↓
Usuario clica "Aprovar"
        ↓
Backend: PATCH incident no ServiceNow
         INSERT histórico no SQLite
        ↓
Dashboard: "✓ Processado em 0.8s"
```

---

## 🎨 Identidade Visual

**Conceito:** "Mesa de Despacho" (Swiss industrial print): cantos retos, traço estrutural pesado, tipografia condensada
grande (Bahnschrift, fonte do próprio Windows: sem fonte externa, a rede corporativa pode bloquear), rótulos em Consolas.

- **Tokens** em `dashboard/src/index.css` (`--c-*`), com **modo claro (papel) e escuro (grafite: fundo `#1f2226`, traço cinza
  médio `#7d848c`; nada de preto com borda branca, pedido do Victor em 02/10)**. O tema segue o sistema
  e o botão no cabeçalho salva a escolha (`localStorage`, sempre em try/catch). Lógica em `src/lib/theme.js`.
- **Cor por estado:** vermelho = pendente/bloqueio, verde = despachado, âmbar = dry-run/atenção, cobalto = ação, magenta = mock/LLM.
- **Cor por unidade:** `unitColor()` em `components/ui.jsx` (tira do ticket, gráficos). Unidade nova = uma linha no mapa.
- **Segurança no gesto:** despachar exige **segurar o botão 0,45 s** (`HOLD_MS` em `components/HoldButton.jsx`); na fila, **Shift+clique** seleciona uma faixa,
  **Ctrl+clique** alterna, e uma barra despacha o lote (mesmo gesto, um `/approve` por vez; só pendentes com destino e título padronizado); casos sem destino ficam com o botão hachurado e bloqueado;
  dry-run sempre visível no cabeçalho; carimbo "DESPACHADO" confirma (simulado ou gravado).
- **Cabeçalho = régua única:** toda célula (abas, ServiceNow, estado API/IA, relógio, tema, engrenagem, modo de escrita) tem a mesma
  altura, divisória e tipografia. ServiceNow fica logo após as abas, **verde vivo (`--c-sn`) com texto preto**, sempre visível.
  Texto pequeno foi ampliado 25% (`--text-xs` 15px, `--text-sm` 16px, `[11.25px]`, `[12.5px]`, `[13.75px]`).
- Protótipos das 3 direções avaliadas: `dashboard/public/design/` (A foi a escolhida).

---

## 🤖 LLM e Agente

- **IA só via 9router** (`data/llm.json`, um único provedor: `http://localhost:20128/v1`, chave `NINEROUTER_API_KEY` no `.env`).
  Quais modelos existem e o fallback entre eles é gerido no próprio 9router; o agente só garante o caminho até ele.
  Ícone de **engrenagem** no cabeçalho → **Configurações**: modelo de texto/visão, URL, timeout, teste (texto, ferramentas, visão),
  estado do despacho e da lista de servidores. Código: `backend/llm.py`.
- **Validação SCOM automática** (`POST /incidents/{n}/ping`, bloco "Alerta SCOM · validação automática" no detalhe, sem botão):
  abriu um SCOM pendente, roda `ping -n 10` sozinho e desenha a **saída real** num PNG (Pillow, Consolas;
  `scom.render_evidence`, `data/evidencias/ping_<INC>_<HOST>.png`; não abre janela). `scom.ultima_validacao` vale se o
  **último** ping do incidente deu OK há até 30 min e a imagem existe. Aí a prévia/`/approve` trocam "Encaminhado para equipe."
  pela `scom.WORK_NOTE` e o despacho **anexa a imagem antes do PATCH** (sem duplicar; falha no anexo = nada enviado).
  SCOM já despachado: "Registrar validação" (`POST /incidents/{n}/ping/registrar`, segurar): anexa + work note, sem mudar estado.
  Lista de servidores em `data/servidores.csv` (export de "Gestão De Servidores", fora do git); `backend/servidores.py` lê só
  colunas seguras, nunca senhas/iLO/chaves; a ficha do servidor citado aparece no detalhe.
- **Nota do despacho** (`payload.build_first_touch(..., contexto)`): editada > validação SCOM recente > câmera testada com print
  anexado ("Encaminhado para equipe. Teste da câmera X às HH:MM: imagem normalizada no Digifort, print anexado.") > padrão.
  Impacto/urgência (`ApproveIn.impact`/`urgency`, 1-4, em Editar) vão no PATCH e somam a linha de severidade à nota.
- **Evidência de câmera (Digifort)** (`backend/digifort.py`, `routes/camera.py`, painel "Evidência da câmera" no detalhe): o
  "Número do Objeto" do incidente (`camera_codigo`, lido do formulário) é procurado como nome de câmera nos servidores CFTV da
  unidade (lista de servidores); confere `GetStatus` (voltou?) e só então tira o snapshot (`GetSnapshot`, com nome e hora na imagem,
  salvo em `data/evidencias/`). Anexar ao incidente = gesto de segurar, sem duplicar, respeita dry-run. Só leitura no Digifort.
  Credencial padrão em `DIGIFORT_USER`/`DIGIFORT_PASSWORD` no `.env`; servidor com senha diferente: `data/digifort_credenciais.json`
  (`{"10.58.8.27": {"usuario": "", "senha": ""}}`, fora do git). Nunca lida das colunas de senha da planilha.
  Docs da API em `API-DIGIFORT/` (porta 8601). Servidores 7.3 (API 1.9.1) ignoram a marca d'água nativa: a faixa com a hora do
  servidor é desenhada por nós (Pillow) abaixo da imagem; a data de 2000 no vídeo é gravada pela própria câmera.
- **Busca tolerante de câmera** (`digifort.inventario`/`pontuar`/`candidatas`/`locate`): o solicitante quase nunca escreve o nome
  exato. Cada servidor da unidade é lido inteiro (2 chamadas: `GetCameras` com Name/Description/Active/Group + `GetStatus`,
  cache em memória de 10 min; API antiga sem esses campos → refaz só com Name) e comparado localmente: nome igual ignorando
  separadores e zeros à esquerda (`MDE 11` = `MDE-011`) = 100; prefixo + número contidos = 90; contido = 80; palavras na
  descrição ("portaria", "balança") 50-75; semelhança de texto. Escolhe sozinha só com **uma** câmera >=90 (mesmo nome em
  principal e reserva conta como uma; a cópia ativa vence). Fora isso a tela lista as candidatas e "Testar esta" manda
  `escolha {consulta, ip, nome}` (só servidor da unidade), que fica lembrada em `data/digifort_cache.json`. Texto livre sem
  código ("câmera da MR4") nunca escolhe sozinho; depois da escolha o incidente passa a usar o nome real (print e nota).
  Lembrada que está **desativada** (servidor reserva) não encerra a busca: procura a cópia ativa e reaprende.
  `DigifortError.tipo`: credencial | timeout | rede | config | resposta.
- **Aba Câmeras e servidores** (`pages/CameraPage.jsx`): sub-abas **Topologia** (padrão) e **Teste de câmera** (incidente
  vindo de outra tela abre direto no teste).
  - **Topologia** (`components/TopologiaMapa.jsx`, estilo Packet Tracer): cada unidade é um nó (switch, cor da unidade,
    disponibilidade e barra) ligado por cabos aos servidores (ícone de servidor com LEDs). Cabo/LED: verde >= 95%, âmbar
    85-95%, vermelho < 85% ou servidor sem leitura; tracejado = reserva (todas desativadas) ou não lido. **Disponibilidade =
    câmeras transmitindo ÷ câmeras ativas** (desativadas fora; a mesma câmera no principal e no reserva conta uma vez, com o
    melhor estado). `GET /servidores/topologia/mapa?forcar=` (`backend/topologia.py`: `resumir` puro + `ler_todos`, 8
    servidores em paralelo, cache de 10 min do inventário; ~12 s a frio para 62 servidores). Clique na unidade ou no servidor
    abre o **card** com todas as câmeras por servidor (`GET /servidores/topologia/{ip}`, só IP da lista), filtro por nome e
    estado (sem sinal / desativadas / transmitindo), tempo sem sinal e INC aberto que cita a câmera (leva ao teste).
    Ordem A-Z ou pior primeiro. Leitura de 02/10: 89% da rede; 40 de 62 servidores respondendo.
  - **Teste de câmera** (`components/CameraPanel.jsx`, rotas em `routes/camera.py`): vale para incidente da fila local **ou
    já em andamento** (lido direto do ServiceNow; a unidade vem da regra/campo/prefixo aprendido/grupo, ou você escolhe).
    Fluxo: testar -> anexar print (segurar) -> texto de encerramento editável -> **Registrar work note** (só a nota, segue
    aberto) e/ou **Encerrar incidente** (`POST /incidents/{n}/camera/close`, segurar: state 6, close_code Solved,
    close_notes + work note; exige print gerado e anexado, confere no SN se já está encerrado (6/7/24) e não repete a work
    note já registrada; respeita dry-run). Snapshot espera até 30 s (a 1ª imagem de uma câmera leva ~6 s).
  - Credenciais em 02/10: Piracicaba CFTV04 e WIN-T23VM0PRR3M recusam a senha (falta entrada em
    `digifort_credenciais.json`); Feira de Santana também.
  - **Leitura salva do mapa** (`data/topologia_cache.json`, fora do git): o mapa abre sempre na última leitura (0,1 s, mostra
    "leitura de dd/mm HH:MM", âmbar se > 2 h) e só relê o Digifort em "Atualizar leitura" (~10 s) ou sem leitura salva.
    Guarda as leituras brutas por IP; o resumo é recalculado a cada abertura (esconder/mostrar servidor vale na hora).
  - **Configurações › Servidores** (`pages/ServidoresConfigPage.jsx`, `GET /servidores/config`): servidores por unidade com
    o estado da última leitura (filtro Com falha / Escondidos / Todos). **Senha** própria por servidor
    (`POST /servidores/credencial/{ip}` grava em `digifort_credenciais.json` e já relê o servidor; a senha nunca volta na
    lista), "Voltar à padrão", **Reler** um servidor e **Esconder do mapa** (`PUT /servidores/{ip}/desabilitado`,
    `data/servidores_config.json`): escondido não é lido nem desenhado; unidade sem servidor visível some. O teste de câmera
    continua procurando em todos os servidores da unidade.
  - Números puros do mosaico ("Nome do ponto de imagem: 399, 407, 72 394") valem como códigos quando o campo "Número do
    Objeto" não vem (incidente lido direto do SN). O teste vai até 12 câmeras por incidente (`MAX_CAMERAS`).
- **Navegação** (`App.jsx`, `Header.jsx`, `components/Secoes.jsx`): abas Operação · Câmeras e servidores · Backlog (sub-abas
  Backlog | Tasks). No cabeçalho: botão **IA** (magenta, lâmpada = 9router ligado) abre o Agente; célula de **métricas** (barras
  de despachos dos últimos 7 dias, `GET /metrics/serie`, + % auto) abre Métricas (com a faixa de KPIs no topo);
  engrenagem abre **Configurações** com sub-abas Geral · Regras · Histórico. `go('settings', 'regras')` abre direto a seção.
- **SLA** (`incidents.due_date`, UTC, gravado na análise e atualizado na reconciliação em lote): cartão e detalhe mostram
  "aberto 02/10 09:12 · vence …" em horário de Brasília (`ui.dataSN`, `ui.prazoSLA`: vencido ou < 4 h vermelho, hoje/amanhã
  âmbar). Antes a abertura saía 3 h adiantada (UTC lido como hora local).
- **Aprendizado** (`backend/learning.py`, Configurações › Regras > "Sugestões aprendidas"): o código da câmera (campo "Número do Objeto"; vazio,
  vale o que o texto cita) é lido na análise e nas buscas seguintes (backfill no sync) e entra no texto das regras. Prefixo
  consistente (ex.: `BM-` -> Barra Mansa, >=2 incidentes, >=80%) vira sugestão de regra; aceitar cria a regra e reavalia os pendentes
  sem destino. **Edição manual**: incidente sem localidade/grupo pode ser despachado escolhendo a fila em Editar (`/rules/destinos`).
- **Código da câmera ("Número do Objeto")**: o id da variável muda conforme o formulário de abertura, então
  `servicenow_api.camera_code_from_form` acha o campo pelo **rótulo** ("... (Número do Objeto)"). Página sem o formulário =
  `None` (tentar de novo), formulário sem valor = `''`. Leitura vazia nunca apaga um código bom (`db.save_incident`), e vazio
  é relido a cada 30 min (`camera_lido_em`). `payload.field_codes` entende "MDE 011, 001" (herda o prefixo) e frases com
  vários códigos. O título é calculado na hora (`display_title`), nunca gravado. **Reler**: botão no detalhe
  (`POST /incidents/{n}/refresh`) e "Reler pendentes" na fila (`POST /incidents/refresh-pendentes`): só leitura no SN,
  sem LLM, status mantido.
- **RITM de acompanhamento** (`backend/ritm.py`, `RitmPanel.jsx`): envio pela **API do catálogo** (`order_now` do item
  `58ce7680…`, variáveis `location_00` (sys_id de `cmn_location`), `subrea_00`, `pendncia_00`,
  `descrio_detalhada_do_problema_00`; centro de custo/empresa/departamento vão explícitos, lidos do usuário). Formulário do
  portal (headless) só se o catálogo der 403/404. Localidades do formulário em `data/ritm_locais.json` (gerado por
  `scripts/inspect_ritm_item.py`, só leitura) e a padrão por unidade em `mapeamentos.json` (`ritm_local`). Vale para
  incidente da fila **ou já em andamento** (aba Câmeras). Criar = gesto de segurar; travas: já criada, duplicidade do dia
  (INC ou câmeras), pendência válida. Depois: work note com o número, rascunho Teams, planilha.
- **Pedido de acesso às câmeras (LGPD)** (`payload.is_access_request`; "sem acesso às câmeras" é falha, não pedido): título
  `[Cidade] - Solicitação de acesso às câmeras`, work note de orientação da skill no despacho, selo ACESSO na fila e
  rascunho Teams com `[LINK]` (`teams-draft` com `modelo: "acesso"`). Nunca encerra.
- **Alertas automáticos (TrueSight/SCOM: heartbeat, uso de banda, disco...)**: decisão do Victor em 01/10/2026, diferente da
  skill: vão para a **fila da unidade do servidor**. O servidor vem do texto (`on computer RES-APP-CFTV04`) **ou do IC afetado**
  (`LCB - PRJ-APP-CFTV02`); unidade pela lista de servidores (coluna Unidade), senão pelo prefixo (`scom.HOST_PREFIXO`);
  servidor `PRJ-*`/de Projects → AMS-TI-CFTV-PRJ (ex.: INC4009541, banda em PRJ-APP-CFTV02). Alerta = `scom.is_auto_alert`
  (texto conhecido ou solicitante "LCB, MONITORING"): título, categoria e serviço continuam os do alerta. Entram na fila e nas
  métricas como os demais.
- **Pistas fora do texto** (`backend/pistas.py`, bloco "Pistas" no detalhe): IC afetado (servidor, IC padrão da unidade do
  `mapeamentos.json` ou sigla no fim, `SRV-CFTV-GUA`), local do IC (`cmdb_ci.location`, "Longos - USINA PIRACICABA") e local do
  solicitante. Lidas na mesma consulta do incidente (`servicenow_api.INCIDENT_FIELDS`), gravadas em `incidents.pistas`.
  Sem localidade pelo texto, a pista mais forte decide (IC 80, local 75); IC apontando outra unidade que o texto baixa a
  confiança para 60 e o LLM não desempata.
- **Entrada e Saída da fila** (`backend/fluxo.py`, uma regra só): `analisado` = **Entrada** (Novo na AMS-TI-CFTV, sem work note
  minha); `aprovado` = despachado pelo agente; `tratado_fora` = saiu sem o agente (outro estado, outra fila ou nota minha, autor
  lido do cabeçalho da work note: `sys_journal_field` não é legível pela sessão); `encerrado` = SN 6/7/24 (8 = Aguardando
  Mudança, **não** encerra). `fluxo.reconciliar` confere tudo numa consulta em lote (`sn_api.estado_lote`) no ciclo do sync e
  no "Reler Entrada"; `GET /incidents` só lê o banco. Reanálise nunca devolve à Entrada (`db.save_incident`). Fila com abas
  Entrada / Sem destino / Saída · 24h (`GET /incidents/saida`). Botões por etapa: Entrada = despachar, editar, reler;
  Saída = RITM, e-mail A4, Teams (acesso), registrar validação SCOM e **Encerrar** (`POST /incidents/{n}/close`, segurar,
  dry-run, fluxo 9.3 da skill: state 6, close_code Solved, close_notes + work note; recusa incidente da Entrada).
- **Chamados A4 (UWB/automação, `backend/a4.py`)**: reconhecidos na hora (`display_title` → `a4`, `a4_fila`). E-mail para
  servicedesk@alertsystem.com.br com cópia ao Felipe: texto do modelo `A4 CHAMADOS.oft` guardado em `data/a4_queues.json`
  (`email_template.corpo`, editável), preenchido por `a4.email_a4` (saudação pela hora, descrição útil, solicitante, SLA em
  Brasília). `GET /incidents/{n}/email-a4/preview` mostra; "Abrir no e-mail" usa **`mailto:`** no navegador (Outlook clássico ou
  novo, o que for padrão) e só registra no histórico. **Sem COM/pywin32**: o Outlook novo não tem COM e o clássico ficava
  rodando oculto (`-Embedding`) e travava o servidor; o módulo antigo está em `cftv-agent-arquivo/backend/outlook_com.py`.
  O agente nunca envia e-mail.
- **Métricas** (`backend/insights.py`, funções puras; `GET /metrics/painel`; `pages/MetricsPage.jsx`): três faixas.
  *Para agir agora*: onda de SLA (dia/janela com mais prazos, por equipe, e vencidos), câmera que voltou no último teste e ainda
  sem nota (pode encerrar), câmera **desativada no cadastro** do Digifort (não é rede), parados há 2+ dias sem nota
  (`ultima_nota`), RITMs abertas e de quem dependemos (planilha lida só leitura por `controle.read_rows`), sem localidade.
  *Onde dói*: setores (prefixo do código, `insights.area`) e câmeras crônicas cruzando fila + backlog + RITMs, lote LORA.
  *Agente*: despachos, mediana até despachar, % sem edição/LLM, reanálises e o **retrato diário do backlog** (tabela
  `backlog_diario`, gravado a cada leitura real do backlog; a tendência aparece com 3+ dias). INC clicável: ServiceNow, ou aba
  Câmeras nos cartões de câmera (`App` passa `go(tab, inc)`/`target` às páginas).
- **Tasks** (sub-aba **Tasks** do Backlog, `backend/tasks.py`, `GET /tasks`, `pages/TasksPage.jsx`): só visualização, sem automação. Board
  "TASKs" do time (vtb `9fd80702…`, tabela `sc_task`, mesmo filtro de filas) restrito às de **acesso a imagens** (itens
  `776d895f…` "Solicitação de Acesso as Imagens – CFTV" e `d2e1e278…` "Digifort", de Pecém). Os dados vêm do texto da tarefa
  (`parse_descricao`: só chaves conhecidas; o resto continua o campo anterior). "Comigo" = `assigned_to.user_name` igual ao
  usuário da sessão. Quadro por unidade (mais antigas primeiro) ou tabela; cache de 60 s.
- **Agente** (tela **Agente**, `backend/agent.py`, `POST /agent/chat`): pedidos em texto e prints (Ctrl+V). O print é transcrito
  por um modelo com visão e depois o laço de ferramentas roda só com texto. Ferramentas **somente leitura**: `listar_fila`,
  `consultar_incidentes`, `propor_primeira_tratativa`. Ações viram proposta; a execução é o `/approve` (dry-run, duplicidade),
  confirmada com o gesto de segurar. Só incidentes em estado Novo entram na Entrada.
- **Tratar pelo Backlog** (`pages/BacklogPage.jsx`, `Tratar`): clicar num incidente (tabela ou quadro) abre ao lado os
  mesmos painéis da Operação: teste de câmera (print, work note, encerrar), RITM e Encerrar (segurar). `POST /close` aceita
  incidente fora da fila local: confere o estado no ServiceNow (encerrado 6/7/24 ou ainda Novo = recusa). Respeita o dry-run.
- **Tasks ocultas**: `data/tasks_ocultas.json` (`{"TASK...": "motivo"}`) tira casos pontuais do painel de Tasks.
- Testes nunca chamam LLM real nem o ServiceNow (`tests/conftest.py`).

---

## 🔑 Variáveis de Ambiente (.env)

```bash
# LLM (edge cases) — OpenRouter tem prioridade
OPENROUTER_API_KEY=sk-or-...
# OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
# ANTHROPIC_API_KEY=sk-...      # fallback

# ServiceNow
SERVICENOW_INSTANCE=amamericas
SERVICENOW_TOKEN=...            # Gerar em SN admin panel
SERVICENOW_DRY_RUN=true         # false só após validar contra a instância real

# App
APP_ENV=development             # ou production
DEBUG=True
```

**NÃO COMMITTAR .env — adicionar a .gitignore**

---

## 📝 Regras Padrão (data/rules.json)

```json
{
  "rules": [
    {
      "id": 1,
      "pattern": "PIR|Piracicaba",
      "localidade": "Piracicaba",
      "grupo": "287a11d0dbd9b7c0e5f36451ca961955",
      "grupo_display": "AMS-TI-CFTV-PIR",
      "ritm_necessaria": false,
      "categoria": "network",
      "subcategory": "Telecom"
    },
    {
      "id": 2,
      "pattern": "MDE|Monlevade",
      "localidade": "João Monlevade",
      "grupo": "e07a11d0dbd9b7c0e5f36451ca96194e",
      "grupo_display": "AMS-TI-CFTV-MDE",
      "ritm_necessaria": true,
      "categoria": "network",
      "pendencia": "Infraestrutura"
    },
    {
      "id": 3,
      "pattern": "fibra.*rompida|ruptura",
      "localidade": null,
      "ritm_necessaria": true,
      "categoria": "network",
      "pendencia": "Redes"
    }
  ]
}
```

**Editar via Dashboard (aba "Regras") ou manualmente + refresh.**

---

## 🧠 Custo de Tokens

| Operação | Tokens | Frequência |
|---|---|---|
| Localidade ambígua | 100 | 1-2/dia |
| Decisão RITM | 80 | 1-2/dia |
| Novo padrão | 150 | 2-3/semana |
| **Total/dia** | **200-300** | **vs. 5k-10k via chat** |

---

## 🛠️ Atalhos úteis

**Adicionar uma regra:**
```javascript
// dashboard/src/pages/RulesPage.jsx
const newRule = {
  pattern: "BM|Barra Mansa",
  localidade: "Barra Mansa",
  grupo: "e87a11d0dbd9b7c0e5f36451ca961930",
  grupo_display: "AMS-TI-CFTV-DBB",
  ritm_necessaria: true
};
await api.post("/rules", newRule);
```

**Chamar Claude (raro):**
```python
# backend/claude_caller.py
from anthropic import Anthropic
client = Anthropic()

def identify_localidade(desc: str):
    msg = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=50,
        messages=[{"role": "user", "content": f"Localidade: {desc}"}]
    )
    return msg.content[0].text.strip()
```

**Query SQLite:**
```python
# backend/db.py
import sqlite3

def get_incidents_by_localidade(localidade: str):
    conn = sqlite3.connect("data/cftv.db")
    c = conn.cursor()
    c.execute("SELECT * FROM incidents WHERE localidade = ?", (localidade,))
    return c.fetchall()
```

**Resetar banco:**
```bash
rm data/cftv.db
python scripts/setup_db.py
```

---

## 📚 Referências

- **IMPLEMENTACAO.md** — Setup, troubleshooting, deploy
- **requirements.txt** — Dependências Python
- **servicenow-api** — https://docs.servicenow.com/en/now/platform/integrate/reference/api-rest/table-api-overview.html
- **FastAPI** — https://fastapi.tiangolo.com/
- **TailwindCSS** — https://tailwindcss.com/

---

## 📍 Localidades (02/10/2026)

- **Mina do Andrade** (regra #21): padrão AND, Andrade → AMS-TI-CFTV-BZD | IC: LCB-SRV-CFTV-AND01
- **AM PECEM** (regra #22): padrão PEC, PECEM, Pecém → FCB-INFRA-CFTV-PEC | IC: LCB-SRV-CFTV-PEC01
- **Belgo Contagem** (regra #23): padrão CTG, GATC, Arames, Belgo Contagem → AMS-TI-CFTV-ARAMES-CTG | IC: LCB-SRV-CFTV-CTG01

**Textos padrão (04/10/2026)**

**SCOM heartbeat (fluxo 5.1):**
```
Causa raiz: Falha de heartbeat do serviço System Center Management no servidor [HOST].Americas.mittalco.com.
Resolução: Serviço verificado e validado, operando normalmente sem necessidade de intervenção.
Encerramento: Incidente encerrado.
```

**Solicitação de acesso às câmeras (LGPD, encerramento):**
```
Acesso às câmeras foi liberado no Digifort conforme solicitado.
Acesso permitido para o período de 90 dias a partir de hoje, renovável.
Incidente encerrado.
```

## ⚡ Próximas Fases

**Fase 2:** Webhook ServiceNow → auto-import incidentes  
**Fase 3:** RITM automática + Teams notificação  
**Fase 4:** ML leve (aprendizado de regras)

---

## 👤 Owner & Contato

**Victor Alexandre Basilio Machado**  
Network Analyst @ A4 Solutions / Grupo Alert  
vic.machado@arcelormittal.com.br

---

**Última atualização:** 02/10/2026  
**Versão:** 0.2 (queue logic, pistas, encerramento, A4, 3 localidades)


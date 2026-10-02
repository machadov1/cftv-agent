import sys
import time
from pathlib import Path

# Permite `python backend/main.py` (raiz do projeto no sys.path)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.config import config
from backend.db import init_db
from backend.routes import incidents, rules, history, metrics, backlog as backlog_routes, llm as llm_routes, agent as agent_routes, sync as sync_routes, session as session_routes, servidores as servidores_routes, camera as camera_routes, tasks as tasks_routes, textos as textos_routes
from backend.sn_session import session
from backend import sync

# Init
init_db()

app = FastAPI(title="CFTV Agent", version="0.2")

# CORS (dashboard local)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(incidents.router)
app.include_router(rules.router)
app.include_router(history.router)
app.include_router(metrics.router)
app.include_router(session_routes.router)
app.include_router(sync_routes.router)
app.include_router(backlog_routes.router)
app.include_router(llm_routes.router)
app.include_router(agent_routes.router)
app.include_router(servidores_routes.router)
app.include_router(camera_routes.router)
app.include_router(tasks_routes.router)
app.include_router(textos_routes.router)

@app.get("/health")
def health():
    return {
        "status": "ok",
        "timestamp": time.time(),
        "llm_enabled": config.llm_enabled,
        "servicenow_dry_run": config.SERVICENOW_DRY_RUN or config.SERVICENOW_MOCK,
        "servicenow_mock": config.SERVICENOW_MOCK,
    }

@app.get("/mock/incidents")
def mock_incidents():
    """Incidentes fictícios disponíveis (só em modo mock)"""
    if not config.SERVICENOW_MOCK:
        return []
    from backend.servicenow_mock import MOCK_INCIDENTS
    return [{"incident_number": k, "short_description": v["short_description"]}
            for k, v in MOCK_INCIDENTS.items()]

# Servir frontend (React build) — ÚLTIMO para não interceptar rotas de API
dashboard_dist = Path(__file__).parent.parent / "dashboard" / "dist"
if dashboard_dist.exists():
    app.mount("/", StaticFiles(directory=str(dashboard_dist), html=True), name="static")

@app.on_event("startup")
def _startup():
    session.start_keepalive()
    sync.start_loop()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=config.API_HOST, port=config.API_PORT, reload=config.DEBUG)

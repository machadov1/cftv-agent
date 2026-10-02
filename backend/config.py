import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")

def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")

class Config:
    """App configuration"""
    # LLM: só via 9router (data/llm.json); a chave vem do .env (NINEROUTER_API_KEY).
    SERVICENOW_INSTANCE = os.getenv("SERVICENOW_INSTANCE", "amamericas")
    SERVICENOW_TOKEN = os.getenv("SERVICENOW_TOKEN")
    # Enquanto True, "Aprovar" NÃO escreve no ServiceNow (só registra localmente).
    SERVICENOW_DRY_RUN = _bool("SERVICENOW_DRY_RUN", "true")
    # True = incidentes fictícios, nenhuma chamada ao ServiceNow nem ao LLM, banco separado.
    SERVICENOW_MOCK = _bool("SERVICENOW_MOCK", "false")

    # Planilha de controle das RITMs (skill, seção 14). Só é gravada fora do dry-run/mock.
    CONTROLE_XLSX = os.getenv(
        "CONTROLE_XLSX",
        r"C:\Users\Victor\OneDrive - Alert System\Documentos\ANALISTA\Controle de Requisições de acompanhamento.xlsx")

    # Digifort (snapshot/status das câmeras). Conta de serviço só com direito de live view; nunca lida da planilha.
    DIGIFORT_USER = os.getenv("DIGIFORT_USER", "")
    DIGIFORT_PASSWORD = os.getenv("DIGIFORT_PASSWORD", "")
    DIGIFORT_PORT = int(os.getenv("DIGIFORT_PORT", "8601"))
    DIGIFORT_TIMEOUT = float(os.getenv("DIGIFORT_TIMEOUT", "6"))

    # Fila geral monitorada (skill 11.1: AMS-TI-CFTV) e busca automática (somente leitura)
    QUEUE_GROUP = os.getenv("QUEUE_GROUP", "a07a11d0dbd9b7c0e5f36451ca96191d")
    QUEUE_STATES = os.getenv("QUEUE_STATES", "1")  # 1 = Novo
    SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", "120"))

    APP_ENV = os.getenv("APP_ENV", "development")
    DEBUG = _bool("DEBUG", "True")
    API_HOST = os.getenv("API_HOST", "127.0.0.1")
    API_PORT = int(os.getenv("API_PORT", "8000"))

    # Abaixo disso o LLM é consultado
    CONFIDENCE_THRESHOLD = 70

    # Database (caminhos absolutos: independem do diretório de execução)
    DB_PATH = str(ROOT / "data" / ("cftv_mock.db" if SERVICENOW_MOCK else "cftv.db"))
    RULES_PATH = str(ROOT / "data" / "rules.json")

    @property
    def llm_enabled(self) -> bool:
        from backend import llm  # import tardio: llm depende de config
        return llm.available()

config = Config()

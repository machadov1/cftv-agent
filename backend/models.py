from pydantic import BaseModel, field_validator
from typing import Literal, Optional
import re

class IncidentIn(BaseModel):
    incident_number: str

    @field_validator("incident_number")
    @classmethod
    def normalize(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.fullmatch(r"INC\d+", v):
            raise ValueError("Número inválido (esperado INC + dígitos)")
        return v

class ApproveIn(BaseModel):
    """Overrides opcionais; se algum campo divergir da sugestão, conta como edição."""
    localidade: Optional[str] = None
    grupo: Optional[str] = None
    grupo_display: Optional[str] = None
    ritm_necessaria: Optional[bool] = None
    short_description: Optional[str] = None  # título editado
    work_notes: Optional[str] = None          # work note editada (além do título)
    impact: Optional[Literal["1", "2", "3", "4"]] = None   # 4 = baixo; priority é derivada no SN
    urgency: Optional[Literal["1", "2", "3", "4"]] = None

class RitmIn(BaseModel):
    localidade_form: str
    subarea: str
    pendencia: str
    descricao: str
    force: bool = False  # ignora aviso de duplicidade (câmeras/incidente já em RITM de hoje)

    @field_validator("localidade_form", "subarea", "pendencia", "descricao")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Campo obrigatório")
        return v.strip()

class TeamsDraftIn(BaseModel):
    ritm: str = ""                      # vazio só no modelo "acesso"
    modelo: str = "ritm"                # "ritm" | "acesso" (pedido de acesso às câmeras, LGPD)
    pendencia: str = ""
    identificado: Optional[str] = None  # 1-2 frases; se vazio, usa o padrão
    abrir: bool = False                 # abre o chat pré-preenchido (nunca envia)

class ControleIn(BaseModel):
    ritm: str
    req: str
    subarea: str = ""
    pendencia: str
    resumo: Optional[str] = None

class RuleIn(BaseModel):
    pattern: str
    localidade: Optional[str] = None
    grupo: Optional[str] = None
    grupo_display: Optional[str] = None
    ritm_necessaria: bool = False
    categoria: Optional[str] = None
    subcategory: Optional[str] = None
    pendencia: Optional[str] = None

    @field_validator("pattern")
    @classmethod
    def valid_regex(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"Regex inválida: {e}")
        if not v.strip():
            raise ValueError("Pattern vazio")
        return v

class MetricsOut(BaseModel):
    total_processados: int
    pendentes: int = 0
    automacao_percentual: float
    tempo_medio_segundos: float
    chamadas_claude_hoje: int
    precisao_percentual: float

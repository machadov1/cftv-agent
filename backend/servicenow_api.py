import html
import re

import requests
from backend.config import config
from backend.sn_session import session
from backend import filas


class SNAuthError(Exception):
    """ServiceNow recusou a sessão/token (401/403): é preciso reconectar."""


def _check(resp):
    if resp.status_code in (401, 403):
        raise SNAuthError(f"ServiceNow recusou o acesso ({resp.status_code})")
    resp.raise_for_status()


DISPLAY_FIELDS = {"caller_id", "u_incident_location", "assignment_group", "cmdb_ci", "cmdb_ci.location",
                  "caller_id.location", "work_notes"}


def _flat(rec: dict) -> dict:
    """display_value=all devolve {value, display_value} em todo campo: achata para valor bruto
    (e texto de exibição nos campos de referência que o usuário lê)."""
    out = {}
    for k, v in rec.items():
        if isinstance(v, dict) and ("value" in v or "display_value" in v):
            v = (v.get("display_value") or v.get("value")) if k in DISPLAY_FIELDS else v.get("value")
        out[k] = v
    return out


# campos lidos na análise: texto, formulário e as pistas fora do texto (IC afetado e locais) + notas (quem já tratou)
INCIDENT_FIELDS = ("sys_id,number,short_description,description,state,assignment_group,cmdb_ci,cmdb_ci.location,"
                   "opened_at,caller_id,caller_id.location,u_incident_location,u_informal_service,subcategory,work_notes,"
                   "due_date")
ESTADO_FIELDS = "sys_id,number,state,assignment_group,work_notes,due_date"

CAMERA_VAR_IDS = ("ni.QS31b3a8091b315510e8142f07b04bcbf5", "ni.QS4436e00d1b315510e8142f07b04bcb0d")


def camera_code_from_form(page: str) -> str:
    """Valor da variável cujo rótulo cita "Número do Objeto" (ou dos ids já conhecidos). '' se não houver."""
    ids = [m.group(1) for m in re.finditer(r'<label[^>]*for="(ni\.QS[0-9a-f]{32})"[^>]*>(.{0,400}?)</label', page, re.S)
           if re.search(r'Objeto', m.group(2), re.I)]
    for vid in ids + [i for i in CAMERA_VAR_IDS if i not in ids]:
        m = re.search(r'<input[^>]*id="' + re.escape(vid) + r'"[^>]*?value="([^"]*)"', page)
        code = html.unescape(m.group(1)).strip() if m else ""
        code = re.sub(r"[^\w\-./, ]", "", code)[:120].strip()
        if code:
            return code
    return ""



class ServiceNowAPI:
    def __init__(self):
        self.base_url = f"https://{config.SERVICENOW_INSTANCE}.service-now.com"
        self.token = config.SERVICENOW_TOKEN
        self._meu_nome: tuple[str | None, str | None] = (None, None)

    def _client(self):
        """(http, headers): sessão do navegador se conectada, senão token estático do .env."""
        http = session.http()
        if http:
            return http, session.headers()
        return requests, {
            'X-UserToken': self.token or '',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

    def get_incident(self, incident_number: str):
        """Buscar incidente no ServiceNow"""
        if config.SERVICENOW_MOCK:
            from backend import servicenow_mock
            return servicenow_mock.get_incident(incident_number)
        http, headers = self._client()
        params = {
            'sysparm_query': f'number={incident_number}',
            'sysparm_fields': INCIDENT_FIELDS,
            'sysparm_display_value': 'all',
        }
        try:
            resp = http.get(f"{self.base_url}/api/now/table/incident", params=params, headers=headers, timeout=15)
            _check(resp)
            result = resp.json().get('result', [])
            return _flat(result[0]) if result else None
        except SNAuthError:
            raise
        except Exception as e:
            print(f"Erro buscando incidente: {e}")
            return None

    def get_camera_code(self, sys_id: str):
        """'Número do Objeto' (código da câmera): variável do formulário, fora da Table API. Só leitura.
        O id da variável muda conforme o formulário de abertura: acha pelo rótulo ("... (Número do Objeto)").
        '' = formulário lido sem valor; None = não consegui ler (tentar de novo depois)."""
        if config.SERVICENOW_MOCK or not sys_id:
            return None
        http, headers = self._client()
        try:
            resp = http.get(f"{self.base_url}/incident.do", params={'sys_id': sys_id, 'sysparm_view': 'amsla'},
                            headers={'X-UserToken': headers.get('X-UserToken', '')}, timeout=60, allow_redirects=False)
            if resp.status_code != 200 or 'incident.short_description' not in resp.text:
                return None  # login/redirect ou outra página: não é "campo vazio"
            return camera_code_from_form(resp.text)
        except Exception as e:
            print(f"Erro lendo código da câmera: {e}")
            return None

    def list_queue(self, limit: int = 50):
        """Incidentes da fila geral (QUEUE_GROUP) nos estados QUEUE_STATES, mais novos primeiro. Somente leitura."""
        if config.SERVICENOW_MOCK:
            from backend import servicenow_mock
            return servicenow_mock.list_queue()
        http, headers = self._client()
        params = {
            'sysparm_query': f'assignment_group={config.QUEUE_GROUP}^stateIN{config.QUEUE_STATES}^ORDERBYDESCsys_created_on',
            'sysparm_fields': INCIDENT_FIELDS,
            'sysparm_display_value': 'all',
            'sysparm_limit': limit,
        }
        resp = http.get(f"{self.base_url}/api/now/table/incident", params=params, headers=headers, timeout=20)
        _check(resp)
        return [_flat(r) for r in resp.json().get('result', [])]

    def estado_lote(self, sys_ids: list[str]) -> list[dict]:
        """Estado atual (state, grupo, notas) de vários incidentes numa consulta por bloco de 80. Somente leitura.
        Cada item: {sys_id, number, state (código), grupo (sys_id), grupo_nome, work_notes (texto exibido)}."""
        if config.SERVICENOW_MOCK or not sys_ids:
            return []
        http, headers = self._client()
        out = []
        for i in range(0, len(sys_ids), 80):
            bloco = sys_ids[i:i + 80]
            resp = http.get(f"{self.base_url}/api/now/table/incident", headers=headers, timeout=30, params={
                'sysparm_query': 'sys_idIN' + ','.join(bloco), 'sysparm_fields': ESTADO_FIELDS,
                'sysparm_display_value': 'all', 'sysparm_limit': len(bloco)})
            _check(resp)
            for r in resp.json().get('result', []):
                g = r.get('assignment_group') or {}
                wn = r.get('work_notes') or {}
                st = r.get('state') or {}
                out.append({'sys_id': (r.get('sys_id') or {}).get('value'), 'number': (r.get('number') or {}).get('value'),
                            'state': str(st.get('value') or ''), 'grupo': g.get('value') or '',
                            'grupo_nome': g.get('display_value') or '', 'work_notes': wn.get('display_value') or '',
                            'due_date': (r.get('due_date') or {}).get('value') or None})
        return out

    def meu_nome(self) -> str | None:
        """Nome de exibição do usuário da sessão ("Machado, Victor Alexandre Basilio"), como aparece nas notas."""
        if config.SERVICENOW_MOCK or not session.user:
            return None
        if self._meu_nome[0] == session.user:
            return self._meu_nome[1]
        http, headers = self._client()
        resp = http.get(f"{self.base_url}/api/now/table/sys_user", headers=headers, timeout=15, params={
            'sysparm_query': f'user_name={session.user}', 'sysparm_fields': 'name', 'sysparm_limit': 1})
        _check(resp)
        res = resp.json().get('result', [])
        nome = res[0].get('name') if res else None
        self._meu_nome = (session.user, nome)
        return nome

    def list_backlog(self, limit: int = 300):
        """Incidentes abertos das filas CFTV (estados fora de 6/7/8), por prazo. Valores brutos + de exibição. Somente leitura."""
        http, headers = self._client()
        params = {
            'sysparm_query': f'{filas.grupos_query()}^stateNOT IN{filas.estados_fora()}^ORDERBYdue_date',
            'sysparm_fields': 'number,short_description,description,caller_id,due_date,opened_at,assignment_group,state,priority,sys_updated_by,u_has_breached,u_informal_service,comments_and_work_notes',
            'sysparm_display_value': 'all',
            'sysparm_limit': limit,
        }
        resp = http.get(f"{self.base_url}/api/now/table/incident", params=params, headers=headers, timeout=30)
        _check(resp)
        return resp.json().get('result', [])

    def count_closed_month(self):
        """Incidentes resolvidos no mês: mesmo filtro do relatório 'Incidentes Encerrados no Mês' do painel do ServiceNow."""
        http, headers = self._client()
        q = (f"{filas.grupos_query_encerrados()}^resolved_atONThis month@javascript:gs.beginningOfThisMonth()"
             "@javascript:gs.endOfThisMonth()")
        try:
            resp = http.get(f"{self.base_url}/api/now/stats/incident", headers=headers, timeout=30,
                            params={'sysparm_count': 'true', 'sysparm_query': q})
            _check(resp)
            return int(resp.json()['result']['stats']['count'])
        except SNAuthError:
            raise
        except Exception as e:
            print(f"Erro contando encerrados no mês: {e}")
            return None

    def get_current(self, sys_id: str):
        """Estado atual (state, work_notes) para evitar duplicidade. None se indisponível."""
        if config.SERVICENOW_MOCK:
            from backend import servicenow_mock
            return servicenow_mock.get_current(sys_id)
        http, headers = self._client()
        try:
            resp = http.get(f"{self.base_url}/api/now/table/incident/{sys_id}",
                            params={'sysparm_fields': 'state,work_notes'}, headers=headers, timeout=15)
            _check(resp)
            return resp.json().get('result')
        except SNAuthError:
            raise
        except Exception as e:
            print(f"Erro lendo estado atual: {e}")
            return None

    def get_caller(self, sys_id: str):
        """{'nome': 'Costa, Ericon Sampaio', 'email': ...} do solicitante, ou None."""
        if config.SERVICENOW_MOCK:
            return {"nome": "Costa, Ericon Sampaio", "email": "ericon.costa@example.com"}
        http, headers = self._client()
        try:
            resp = http.get(f"{self.base_url}/api/now/table/incident/{sys_id}", headers=headers, timeout=15, params={
                'sysparm_display_value': 'true', 'sysparm_fields': 'caller_id,caller_id.email'})
            resp.raise_for_status()
            r = resp.json().get('result') or {}
            c = r.get('caller_id')
            nome = c.get('display_value') if isinstance(c, dict) else c
            return {"nome": nome, "email": r.get('caller_id.email')}
        except Exception as e:
            print(f"Erro lendo solicitante: {e}")
            return None

    def list_attachment_names(self, sys_id: str):
        """Nomes dos anexos do incidente (para não anexar duas vezes). None se indisponível."""
        if config.SERVICENOW_MOCK:
            return []
        http, headers = self._client()
        try:
            resp = http.get(f"{self.base_url}/api/now/attachment", headers=headers, timeout=15, params={
                'sysparm_query': f'table_name=incident^table_sys_id={sys_id}', 'sysparm_fields': 'file_name'})
            _check(resp)
            return [a.get('file_name') for a in resp.json().get('result', [])]
        except SNAuthError:
            raise
        except Exception as e:
            print(f"Erro listando anexos: {e}")
            return None

    def attach_file(self, sys_id: str, file_name: str, data: bytes, content_type: str = "image/jpeg"):
        """Anexa arquivo ao incidente (respeita dry-run/mock)."""
        if config.SERVICENOW_MOCK or config.SERVICENOW_DRY_RUN:
            print(f"[DRY-RUN] anexo {file_name} ({len(data)} bytes) em incident/{sys_id}")
            return True
        http, headers = self._client()
        headers = {**headers, 'Content-Type': content_type}
        try:
            resp = http.post(f"{self.base_url}/api/now/attachment/file", params={
                'table_name': 'incident', 'table_sys_id': sys_id, 'file_name': file_name},
                headers=headers, data=data, timeout=60)
            _check(resp)
            return resp.status_code == 201
        except SNAuthError:
            raise
        except Exception as e:
            print(f"Erro anexando arquivo: {e}")
            return False

    def patch_incident(self, sys_id: str, fields: dict):
        """Atualizar incidente no ServiceNow (respeita SERVICENOW_DRY_RUN)"""
        if config.SERVICENOW_MOCK or config.SERVICENOW_DRY_RUN:
            print(f"[DRY-RUN] PATCH incident/{sys_id}: {fields}")
            if config.SERVICENOW_MOCK:
                from backend import servicenow_mock
                servicenow_mock.apply_patch(sys_id, fields)
            return True
        http, headers = self._client()
        try:
            resp = http.patch(f"{self.base_url}/api/now/table/incident/{sys_id}", json=fields, headers=headers, timeout=15)
            return resp.status_code == 200
        except Exception as e:
            print(f"Erro atualizando incidente: {e}")
            return False


sn_api = ServiceNowAPI()

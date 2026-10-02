// Build servido pelo backend: mesma origem. Dev (Vite :3000): 127.0.0.1, porque "localhost" pode resolver para ::1.
const API = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '');

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    const msg = Array.isArray(detail) ? detail.map((d) => d.msg).join('; ') : detail;
    throw new Error(msg || `Erro ${res.status}`);
  }
  return data;
}

const body = (obj) => JSON.stringify(obj);

export const getHealth = () => request('/health');
export const getMockIncidents = () => request('/mock/incidents');
export const processIncident = (incident_number) =>
  request('/incidents', { method: 'POST', body: body({ incident_number }) });
export const approveIncident = (number, overrides = {}) =>
  request(`/incidents/${number}/approve`, { method: 'POST', body: body(overrides) });
export const getIncident = (n) => request(`/incidents/${n}`);
export const getIncidents = (limit = 50) => request(`/incidents?limit=${limit}`);
export const getSaida = (horas = 24) => request(`/incidents/saida?horas=${horas}`);
export const getRules = () => request('/rules');
export const createRule = (rule) => request('/rules', { method: 'POST', body: body(rule) });
export const updateRule = (id, rule) => request(`/rules/${id}`, { method: 'PUT', body: body(rule) });
export const deleteRule = (id) => request(`/rules/${id}`, { method: 'DELETE' });
export const getHistory = (params = {}) => {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  return request(`/history${qs ? `?${qs}` : ''}`);
};
export const getMetrics = () => request('/metrics');
export const getSerie = (dias = 7) => request(`/metrics/serie?dias=${dias}`);
export const getBreakdown = () => request('/metrics/breakdown');
export const getInsights = () => request('/metrics/insights');
export const getPainel = () => request('/metrics/painel');
export const getSession = () => request('/session/status');
export const sessionLogin = () => request('/session/login', { method: 'POST' });
export const getPayload = (n) => request(`/incidents/${n}/payload`);
export const refreshIncident = (n) => request(`/incidents/${n}/refresh`, { method: 'POST' });
export const refreshPendentes = () => request('/incidents/refresh-pendentes', { method: 'POST' });
export const getRitmDraft = (n) => request(`/incidents/${n}/ritm/draft`);
export const createRitm = (n, body_) => request(`/incidents/${n}/ritm`, { method: 'POST', body: body(body_) });
export const teamsDraft = (n, body_) => request(`/incidents/${n}/teams-draft`, { method: 'POST', body: body(body_) });
export const controleRow = (n, body_) => request(`/incidents/${n}/controle`, { method: 'POST', body: body(body_) });
export const getSyncStatus = () => request('/sync/status');
export const syncQueue = () => request('/sync', { method: 'POST' });
export const getBacklog = (force = false) => request(`/backlog${force ? '?force=true' : ''}`);
export const agentChat = (messages, images = []) => request('/agent/chat', { method: 'POST', body: body({ messages, images }) });
export const getLlmConfig = () => request('/llm/config');
export const saveLlmConfig = (cfg) => request('/llm/config', { method: 'PUT', body: body(cfg) });
export const testLlm = (id) => request(`/llm/test/${id}`, { method: 'POST' });
export const getLlmModels = (id) => request(`/llm/models/${id}`);
export const getServidoresStatus = () => request('/servidores/status');
export const getIncidentHost = (n) => request(`/incidents/${n}/host`);
export const pingIncident = (n, host = '') =>
  request(`/incidents/${n}/ping`, { method: 'POST', body: body({ host: host || null }) });
export const pingEvidenceUrl = (n, t = 0) => `${API}/incidents/${n}/ping/evidencia?t=${t}`;
export const pingRegistrar = (n) => request(`/incidents/${n}/ping/registrar`, { method: 'POST' });

export const cameraCheck = (n, localidade = '', escolha = null) =>
  request(`/incidents/${n}/camera/check`, { method: 'POST', body: body({ localidade: localidade || null, escolha }) });
export const getTopologia = () => request('/servidores/topologia');
export const getTopologiaMapa = (forcar = false) => request(`/servidores/topologia/mapa${forcar ? '?forcar=true' : ''}`);
export const getTopologiaServidor = (ip, forcar = false) => request(`/servidores/topologia/${ip}${forcar ? '?forcar=true' : ''}`);
export const cameraClosingDraft = (n) => request(`/incidents/${n}/camera/closing-draft`);
export const cameraClosingNote = (n, texto) =>
  request(`/incidents/${n}/camera/closing-note`, { method: 'POST', body: body({ texto }) });
export const cameraClose = (n, texto) =>
  request(`/incidents/${n}/camera/close`, { method: 'POST', body: body({ texto }) });
export const getDestinos = () => request('/rules/destinos');
export const getSugestoes = () => request('/rules/sugestoes');
export const aceitarSugestao = (prefixo, localidade) =>
  request('/rules/sugestoes/aceitar', { method: 'POST', body: body({ prefixo, localidade }) });
export const cameraAttach = (n) => request(`/incidents/${n}/camera/attach`, { method: 'POST' });
export const snapshotUrl = (n, code, t = 0) => `${API}/incidents/${n}/camera/snapshot/${encodeURIComponent(code)}?t=${t}`;
export const getDigifortStatus = () => request('/digifort/status');
export const getTasks = (force = false) => request(`/tasks${force ? '?force=true' : ''}`);
export const getTasksVolumetria = (meses = 5) => request(`/tasks/volumetria?meses=${meses}`);
export const getIncidentesVolumetria = (meses = 5) => request(`/metrics/volumetria?meses=${meses}`);
export const closeIncident = (n, work_notes) => request(`/incidents/${n}/close`, { method: 'POST', body: body({ work_notes }) });
export const emailA4Preview = (n) => request(`/incidents/${n}/email-a4/preview`);
export const emailA4Abrir = (n) => request(`/incidents/${n}/email-a4`, { method: 'POST' });
